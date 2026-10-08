// REFERENCE ONLY - not part of the SeedArsenal build. It sits outside the mod folder on purpose
// (tModLoader compiles every .cs file under a mod's folder) and nothing in the mod calls it.
//
// The in-game recorder the original showcase mod used for its videos: the scripted scene called
// Start() when it began and Stop() when it ended. Copy it into a mod if you script takes that way;
// to record by hand from outside the game, `fsgc win record` does the same job.
//
// What it took to record tModLoader cleanly:
// - Video: ffmpeg's gfxcapture source (Windows.Graphics.Capture) on the game window's HWND. It gets
//   the GPU frames of that one window, even when it is covered; gdigrab only gives black frames.
//   Don't read the back buffer from inside the game: this FNA3D's D3D11 ReadBackbuffer leaks a
//   full-size staging texture per call (~3.7 MB a frame; one take grew the process to 17 GB).
// - Audio: FAudio on Windows talks to WASAPI directly (SDL_AUDIODRIVER=disk changes nothing), so the
//   game's own sound comes from a WASAPI process-loopback capture of this process
//   (game-changer/game_changer/ps1/ProcLoopback.ps1): the game only, nothing else playing on the PC.
// - Stopping: send ffmpeg a raw 'q' and wait for it OFF the main thread. gfxcapture only delivers a
//   frame when the window redraws, so a game blocked in WaitForExit stalls ffmpeg before it ever
//   reads the q, and the end of the take is lost to the kill that follows.
// - Sync: both captures are stamped with QPC time (Stopwatch). <video>.json gets the stamps and the
//   audio offset, so `fsgc video mux <video> <video>.audio.raw <video>.json out.mp4` lines them up.
//   ffmpeg takes ~0.24-0.3 s from launch to its first frame (measured: the nuke's flash vs its boom).
// - Write .mkv and flush every packet: a killed ffmpeg still leaves a playable file.
// - An unfocused game window is throttled: set Main.instance.InactiveSleepTime = TimeSpan.Zero for a
//   take, or the recording stutters while you work in another window.

using System;
using System.Diagnostics;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using log4net;
using Terraria;

namespace YourMod
{
	public static class InModRecorder
	{
		const double FfmpegStartupS = 0.3; // launch -> first captured frame (same figure as `fsgc win record`)
		static Process ffmpeg, audio;
		static long videoStartHns, audioStartHns = -1;
		static string outPath;
		static ILog log;
		public static bool Running => ffmpeg != null;
		static long NowHns() => (long)(Stopwatch.GetTimestamp() * (10_000_000.0 / Stopwatch.Frequency));

		/// <summary>Records this game's window (and its own sound) to <paramref name="mkvPath"/>.</summary>
		/// <param name="ffmpegExe">a Windows ffmpeg with the gfxcapture filter (`fsgc win setup` fetches one)</param>
		/// <param name="procLoopbackPs1">game_changer/ps1/ProcLoopback.ps1, or null for video only</param>
		/// <param name="logger">e.g. your Mod.Logger</param>
		public static void Start(string mkvPath, string ffmpegExe, string procLoopbackPs1, ILog logger)
		{
			if (Running || Main.dedServ) return;
			outPath = mkvPath;
			log = logger;
			var self = Process.GetCurrentProcess();
			if (procLoopbackPs1 != null && File.Exists(procLoopbackPs1))
			{
				var apsi = new ProcessStartInfo("powershell.exe", $"-NoProfile -ExecutionPolicy Bypass -File \"{procLoopbackPs1}\" -TargetPid {self.Id} -Out \"{outPath}.audio.raw\"")
				{ UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true };
				audio = Process.Start(apsi);
				audio.ErrorDataReceived += (_, e) => { if (!string.IsNullOrEmpty(e.Data)) log.Warn("audio: " + e.Data); };
				audio.BeginErrorReadLine();
				// one JSON line once it is capturing: {"start_hns": <QPC in 100 ns>, "rate": 48000, ...}
				string header = audio.StandardOutput.ReadLine() ?? "";
				var m = Regex.Match(header, "\"start_hns\": (\\d+)");
				audioStartHns = m.Success ? long.Parse(m.Groups[1].Value) : -1;
				log.Info("audio capture: " + header);
			}
			long hwnd = self.MainWindowHandle.ToInt64();
			// h264_nvenc is NVIDIA's encoder; use -c:v libx264 -preset veryfast -crf 18 elsewhere
			var psi = new ProcessStartInfo(ffmpegExe,
				$"-y -loglevel error -f lavfi -i gfxcapture=hwnd={hwnd}:max_framerate=60:capture_cursor=0,hwdownload,format=bgra " +
				$"-vf fps=30,crop=trunc(iw/2)*2:trunc(ih/2)*2 -c:v h264_nvenc -preset p4 -cq 18 -pix_fmt yuv420p -flush_packets 1 \"{outPath}\"")
			{ UseShellExecute = false, RedirectStandardInput = true, RedirectStandardError = true, CreateNoWindow = true };
			videoStartHns = NowHns();
			ffmpeg = Process.Start(psi);
			ffmpeg.ErrorDataReceived += (_, e) => { if (!string.IsNullOrEmpty(e.Data)) log.Warn("ffmpeg: " + e.Data); };
			ffmpeg.BeginErrorReadLine();
			log.Info($"recording window {hwnd:X} to {outPath}");
		}

		public static void Stop()
		{
			if (!Running) return;
			var (f, a) = (ffmpeg, audio);
			ffmpeg = null; audio = null;
			long videoStopHns = NowHns();
			if (f.HasExited) log.Warn($"ffmpeg had already exited (code {f.ExitCode}) at {f.ExitTime:T}");
			// a raw byte: ffmpeg polls stdin for single-key commands. Then wait off the main thread:
			// gfxcapture only yields frames while the window keeps changing, so a blocked game would
			// stall ffmpeg before it ever reads the q (and its last frames would be lost to a kill)
			try { f.StandardInput.BaseStream.WriteByte((byte)'q'); f.StandardInput.BaseStream.Flush(); } catch (IOException) { }
			long aStart = audioStartHns, vStart = videoStartHns;
			string path = outPath;
			Task.Run(() =>
			{
				if (!f.WaitForExit(15000)) { log.Warn("ffmpeg ignored q; killing"); f.Kill(); }
				if (a != null)
				{
					try { a.StandardInput.WriteLine(); a.StandardInput.Flush(); } catch (IOException) { }
					if (!a.WaitForExit(5000)) a.Kill();
					// audio sample 0 is at aStart; the first video frame lands ~FfmpegStartupS after vStart
					double offset = (vStart - aStart) / 1e7 + FfmpegStartupS;
					File.WriteAllText(path + ".json", FormattableString.Invariant(
						$"{{\"video\": \"{Slash(path)}\", \"audio\": \"{Slash(path + ".audio.raw")}\", \"audio_offset_s\": {offset:F3}, \"audio_start_hns\": {aStart}, \"video_start_hns\": {vStart}, \"video_stop_hns\": {videoStopHns}, \"rate\": 48000, \"channels\": 2, \"format\": \"f32le\"}}"));
					a.Dispose();
				}
				log.Info("recording finished: " + path);
				f.Dispose();
			});
		}

		static string Slash(string p) => p.Replace("\\", "/");
	}
}
