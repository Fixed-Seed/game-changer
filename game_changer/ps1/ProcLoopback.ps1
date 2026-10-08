<#
  ProcLoopback: record ONE process's audio (WASAPI process loopback, Windows 10 2004+) to raw float32
  stereo 48 kHz - a game capture with only the game's sound, nothing else playing on the machine.
  No build step: Windows PowerShell 5.1 compiles the embedded C# on start.

    powershell -NoProfile -ExecutionPolicy Bypass -File ProcLoopback.ps1 -TargetPid 1234 -Out C:\caps\take1.audio.raw

  Prints one JSON line when capturing: {"start_hns": <QPC in 100 ns>, "rate": 48000, "channels": 2, "format": "f32le"}.
  Sample 0 of the file is start_hns; packets are placed by their QPC timestamps and gaps are filled with
  silence, so file position = wall time. Stops when stdin gets a line / closes, or the process exits.
  (Many games - FNA/FAudio, Unity, Unreal - talk to WASAPI directly, so SDL/driver tricks can't redirect them.)
#>
param([Parameter(Mandatory = $true)][int]$TargetPid, [Parameter(Mandatory = $true)][string]$Out)

$src = @"
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

public static class ProcLoopback
{
    const int Rate = 48000, Channels = 2, BytesPerFrame = 8;

    [StructLayout(LayoutKind.Sequential)]
    struct WaveFormatEx { public ushort Tag, Channels; public uint SamplesPerSec, AvgBytesPerSec; public ushort BlockAlign, BitsPerSample, Size; }

    [StructLayout(LayoutKind.Sequential)]
    struct ActivationParams { public int ActivationType; public uint TargetProcessId; public int LoopbackMode; }

    [StructLayout(LayoutKind.Sequential)]
    struct PropVariantBlob { public ushort Vt, R1, R2, R3; public uint Size; public IntPtr Data; }

    [ComImport, Guid("72A22D78-CDE4-431D-B8CC-843A71199B6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IActivateAudioInterfaceAsyncOperation
    {
        void GetActivateResult(out int result, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
    }

    [ComImport, Guid("41D949AB-9862-444A-80F6-C261334DA5EB"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IActivateAudioInterfaceCompletionHandler
    {
        void ActivateCompleted(IActivateAudioInterfaceAsyncOperation op);
    }

    [ComImport, Guid("94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAgileObject { }

    [ComImport, Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioClient
    {
        [PreserveSig] int Initialize(int shareMode, uint flags, long bufferDuration, long periodicity, ref WaveFormatEx format, IntPtr session);
        [PreserveSig] int GetBufferSize(out uint frames);
        [PreserveSig] int GetStreamLatency(out long latency);
        [PreserveSig] int GetCurrentPadding(out uint padding);
        [PreserveSig] int IsFormatSupported(int shareMode, IntPtr format, IntPtr closest);
        [PreserveSig] int GetMixFormat(out IntPtr format);
        [PreserveSig] int GetDevicePeriod(out long def, out long min);
        [PreserveSig] int Start();
        [PreserveSig] int Stop();
        [PreserveSig] int Reset();
        [PreserveSig] int SetEventHandle(IntPtr handle);
        [PreserveSig] int GetService([MarshalAs(UnmanagedType.LPStruct)] Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object service);
    }

    [ComImport, Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioCaptureClient
    {
        [PreserveSig] int GetBuffer(out IntPtr data, out uint frames, out uint flags, out ulong devicePosition, out ulong qpcPosition);
        [PreserveSig] int ReleaseBuffer(uint frames);
        [PreserveSig] int GetNextPacketSize(out uint frames);
    }

    [DllImport("Mmdevapi.dll", ExactSpelling = true, PreserveSig = false)]
    static extern void ActivateAudioInterfaceAsync([MarshalAs(UnmanagedType.LPWStr)] string path, [MarshalAs(UnmanagedType.LPStruct)] Guid iid,
        IntPtr activationParams, IActivateAudioInterfaceCompletionHandler handler, out IActivateAudioInterfaceAsyncOperation op);

    sealed class Handler : IActivateAudioInterfaceCompletionHandler, IAgileObject
    {
        public readonly ManualResetEvent Done = new ManualResetEvent(false);
        public void ActivateCompleted(IActivateAudioInterfaceAsyncOperation op) { Done.Set(); }
    }

    static long NowHns() { return (long)(Stopwatch.GetTimestamp() * (10000000.0 / Stopwatch.Frequency)); }

    static volatile bool stop;
    static int exitCode;

    public static int Run(int pid, string outPath)
    {
        // COM activation + capture on an MTA thread (PowerShell's own thread is STA)
        var t = new Thread(delegate() { exitCode = Capture(pid, outPath); });
        t.SetApartmentState(ApartmentState.MTA);
        t.Start();
        var reader = new Thread(delegate() { try { Console.In.ReadLine(); } catch { } stop = true; });
        reader.IsBackground = true;
        reader.Start();
        t.Join();
        return exitCode;
    }

    static int Capture(int pid, string outPath)
    {
        var ap = new ActivationParams(); ap.ActivationType = 1; ap.TargetProcessId = (uint)pid; ap.LoopbackMode = 0; // include the process tree
        IntPtr apPtr = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(ActivationParams)));
        Marshal.StructureToPtr(ap, apPtr, false);
        var pv = new PropVariantBlob(); pv.Vt = 65; pv.Size = (uint)Marshal.SizeOf(typeof(ActivationParams)); pv.Data = apPtr;
        IntPtr pvPtr = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(PropVariantBlob)));
        Marshal.StructureToPtr(pv, pvPtr, false);

        var handler = new Handler();
        IActivateAudioInterfaceAsyncOperation op;
        ActivateAudioInterfaceAsync("VAD\\Process_Loopback", typeof(IAudioClient).GUID, pvPtr, handler, out op);
        if (!handler.Done.WaitOne(10000)) { Console.Error.WriteLine("activation timed out"); return 1; }
        int hr; object iface;
        op.GetActivateResult(out hr, out iface);
        if (hr != 0) { Console.Error.WriteLine("activation failed 0x" + hr.ToString("X8")); return 1; }
        var client = (IAudioClient)iface;

        var fmt = new WaveFormatEx(); fmt.Tag = 3; fmt.Channels = Channels; fmt.SamplesPerSec = Rate; fmt.BitsPerSample = 32;
        fmt.BlockAlign = BytesPerFrame; fmt.AvgBytesPerSec = Rate * BytesPerFrame;
        const uint LOOPBACK = 0x00020000, EVENTCALLBACK = 0x00040000, AUTOCONVERTPCM = 0x80000000;
        hr = client.Initialize(0, LOOPBACK | EVENTCALLBACK | AUTOCONVERTPCM, 2000000, 0, ref fmt, IntPtr.Zero);
        if (hr != 0) { Console.Error.WriteLine("Initialize failed 0x" + hr.ToString("X8")); return 1; }
        var ready = new AutoResetEvent(false);
        client.SetEventHandle(ready.SafeWaitHandle.DangerousGetHandle());
        object svc;
        client.GetService(typeof(IAudioCaptureClient).GUID, out svc);
        var capture = (IAudioCaptureClient)svc;

        using (var file = new FileStream(outPath, FileMode.Create, FileAccess.Write, FileShare.Read))
        {
            long startHns = NowHns(), written = 0;
            Console.Out.WriteLine("{\"start_hns\": " + startHns + ", \"rate\": " + Rate + ", \"channels\": " + Channels + ", \"format\": \"f32le\"}");
            Console.Out.Flush();
            client.Start();
            Process target = Process.GetProcessById(pid);
            byte[] buf = new byte[Rate * BytesPerFrame];
            while (!stop && !target.HasExited)
            {
                ready.WaitOne(100);
                uint n;
                while (capture.GetNextPacketSize(out n) == 0 && n > 0)
                {
                    IntPtr data; uint frames, flags; ulong devPos, qpc;
                    capture.GetBuffer(out data, out frames, out flags, out devPos, out qpc);
                    long at = ((long)qpc - startHns) * Rate / 10000000;
                    if (at > written + Rate / 100) { WriteSilence(file, at - written, buf); written = at; }
                    int bytes = (int)frames * BytesPerFrame;
                    if (bytes > buf.Length) buf = new byte[bytes];
                    if ((flags & 2) != 0) Array.Clear(buf, 0, bytes); else Marshal.Copy(data, buf, 0, bytes);
                    file.Write(buf, 0, bytes);
                    written += frames;
                    capture.ReleaseBuffer(frames);
                }
            }
            long end = (NowHns() - startHns) * Rate / 10000000;
            if (end > written) WriteSilence(file, end - written, new byte[Rate * BytesPerFrame]);
            client.Stop();
        }
        return 0;
    }

    static void WriteSilence(Stream s, long frames, byte[] buf)
    {
        Array.Clear(buf, 0, buf.Length);
        while (frames > 0)
        {
            int n = (int)Math.Min(frames, buf.Length / BytesPerFrame);
            s.Write(buf, 0, n * BytesPerFrame);
            frames -= n;
        }
    }
}
"@

Add-Type -TypeDefinition $src -Language CSharp
exit [ProcLoopback]::Run($TargetPid, $Out)
