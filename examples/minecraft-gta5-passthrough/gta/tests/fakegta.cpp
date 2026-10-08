// A stand-in for GTA V to test the GTA half of the passthrough end to end, before GTA is installed:
// a D3D11 window that renders a checkerboard ground and a red pillar into a reversed-Z depth buffer (like GTA),
// flies its camera in GTA's conventions (z up, heading 0 = +y) and drives Minecraft with it through the same
// WebSocket client, while ReShade (dxgi.dll next to the exe) runs MCPassthrough.fx with the compositor add-on
// compiled in here.
//
//   fakegta.exe [seconds]
#include "../src/compositor.h"
#include "../src/ws.h"
#include <windows.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "d3dcompiler.lib")
#pragma comment(lib, "user32.lib")

namespace
{
	constexpr int kWidth = 1280, kHeight = 720;
	constexpr float kNear = 0.15f, kFar = 10000.0f, kFov = 55.0f;
	constexpr float kGroundZ = 63.6f;        // GTA ground height here; the script levels it to Minecraft y = 64
	const float kYOffset = std::round(kGroundZ) - kGroundZ;

	struct Vertex
	{
		float x, y, z;
		float r, g, b;
		float checker;
	};

	const char *kShader = R"(
cbuffer Frame : register(b0) { float4x4 viewProj; };
struct VSOut { float4 pos : SV_Position; float3 world : WORLD; float3 color : COLOR; float checker : CHECKER; };
VSOut vs(float3 p : POSITION, float3 c : COLOR, float k : CHECKER)
{
	VSOut o; o.pos = mul(viewProj, float4(p, 1)); o.world = p; o.color = c; o.checker = k; return o;
}
float4 ps(VSOut i) : SV_Target
{
	if (i.checker > 0.5)
	{
		float2 f = frac(i.world.xy);
		bool edge = min(min(f.x, 1 - f.x), min(f.y, 1 - f.y)) < 0.02;
		bool even = fmod(floor(i.world.x) + floor(i.world.y), 2.0) == 0;
		float3 c = edge ? float3(0.1, 0.1, 0.1) : (even ? float3(0.35, 0.36, 0.4) : float3(0.55, 0.56, 0.6));
		return float4(c, 1);
	}
	return float4(i.color, 1);
}
)";

	struct Mat
	{
		float m[4][4];
	};

	Mat mul(const Mat &a, const Mat &b)
	{
		Mat r = {};
		for (int i = 0; i < 4; ++i)
			for (int j = 0; j < 4; ++j)
				for (int k = 0; k < 4; ++k)
					r.m[i][j] += a.m[i][k] * b.m[k][j];
		return r;
	}

	// GTA camera conventions: rot = (pitch, roll, yaw) degrees, yaw 0 looks along +y, positive pitch looks up.
	Mat view_proj(const float eye[3], float pitch, float yaw, float fovDeg, float aspect)
	{
		const float d2r = 3.14159265f / 180.0f;
		const float cp = std::cos(pitch * d2r), sp = std::sin(pitch * d2r), cy = std::cos(yaw * d2r), sy = std::sin(yaw * d2r);
		const float f[3] = {-sy * cp, cy * cp, sp};
		float r[3] = {f[1], -f[0], 0};  // forward x up(0,0,1)
		const float rl = std::sqrt(r[0] * r[0] + r[1] * r[1]);
		r[0] /= rl;
		r[1] /= rl;
		const float u[3] = {r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]};
		// view: rows are right, up, -forward (right-handed, camera looks down -z)
		Mat v = {{{r[0], r[1], r[2], -(r[0] * eye[0] + r[1] * eye[1] + r[2] * eye[2])},
				  {u[0], u[1], u[2], -(u[0] * eye[0] + u[1] * eye[1] + u[2] * eye[2])},
				  {-f[0], -f[1], -f[2], (f[0] * eye[0] + f[1] * eye[1] + f[2] * eye[2])},
				  {0, 0, 0, 1}}};
		const float t = std::tan(fovDeg * d2r / 2);
		// reversed Z with a finite far plane: depth = n (f - dist) / (dist (f - n)), 1 at the near plane
		Mat p = {{{1 / (aspect * t), 0, 0, 0},
				  {0, 1 / t, 0, 0},
				  {0, 0, kNear / (kFar - kNear), kNear * kFar / (kFar - kNear)},
				  {0, 0, -1, 0}}};
		return mul(p, v);
	}

	void add_box(std::vector<Vertex> &out, float x0, float y0, float z0, float x1, float y1, float z1, float r, float g, float b)
	{
		const float c[8][3] = {{x0, y0, z0}, {x1, y0, z0}, {x1, y1, z0}, {x0, y1, z0}, {x0, y0, z1}, {x1, y0, z1}, {x1, y1, z1}, {x0, y1, z1}};
		const int faces[6][4] = {{0, 1, 2, 3}, {4, 7, 6, 5}, {0, 4, 5, 1}, {1, 5, 6, 2}, {2, 6, 7, 3}, {3, 7, 4, 0}};
		const float shade[6] = {0.5f, 1.0f, 0.8f, 0.65f, 0.75f, 0.6f};
		for (int i = 0; i < 6; ++i)
		{
			const int *q = faces[i];
			for (int k : {0, 1, 2, 0, 2, 3})
				out.push_back({c[q[k]][0], c[q[k]][1], c[q[k]][2], r * shade[i], g * shade[i], b * shade[i], 0});
		}
	}

	/// Thin yellow edges just outside a Minecraft block's cube (GTA coords), to see alignment directly.
	void add_edges(std::vector<Vertex> &out, float x0, float y0, float z0, float x1, float y1, float z1)
	{
		const float e = 0.025f, o = 0.012f;
		x0 -= o; y0 -= o; z0 -= o; x1 += o; y1 += o; z1 += o;
		for (float y : {y0, y1})
			for (float z : {z0, z1})
				add_box(out, x0, y - e, z - e, x1, y + e, z + e, 1.0f, 0.9f, 0.1f);
		for (float x : {x0, x1})
			for (float z : {z0, z1})
				add_box(out, x - e, y0, z - e, x + e, y1, z + e, 1.0f, 0.9f, 0.1f);
		for (float x : {x0, x1})
			for (float y : {y0, y1})
				add_box(out, x - e, y - e, z0, x + e, y + e, z1, 1.0f, 0.9f, 0.1f);
	}

	/// A tiny stand-in for GTA's player and gameplay camera, driven by the director's {"t":"gta","op":...} ops.
	struct Player
	{
		float x = 0.5f, y = -14.0f, z = kGroundZ + 1.0f; // ped origin ~1 m above the ground, like GTA
		float heading = 0;                               // GTA: 0 = +y
		float relHeading = 0, relPitch = 0;              // gameplay camera relative to the ped
		int view = 1;                                    // 4 = first person
		bool walking = false;
		float tx = 0, ty = 0, speed = 1;
	} g_player;

	double num(const std::string &m, const char *key, double fallback)
	{
		const std::string k = std::string("\"") + key + "\":";
		const size_t at = m.find(k);
		return at == std::string::npos ? fallback : std::atof(m.c_str() + at + k.size());
	}

	std::string compact(const std::string &m)
	{
		std::string out;
		bool inString = false;
		for (char c : m)
		{
			if (c == '"')
				inString = !inString;
			if (inString || (c != ' ' && c != '\t'))
				out += c;
		}
		return out;
	}

	void director_op(const std::string &raw)
	{
		const std::string m = compact(raw);
		auto has = [&](const char *op) { return m.find(std::string("\"op\":\"") + op + "\"") != std::string::npos; };
		Player &p = g_player;
		if (has("teleport"))
		{
			p.x = float(num(m, "x", p.x)); p.y = float(num(m, "y", p.y)); p.z = float(num(m, "z", p.z));
			p.heading = float(num(m, "h", 0)); p.relHeading = 0; p.relPitch = float(num(m, "pitch", 0)); p.walking = false;
		}
		else if (has("walk"))
		{
			p.tx = float(num(m, "x", p.x)); p.ty = float(num(m, "y", p.y)); p.speed = float(num(m, "speed", 1.0)) * 1.4f; p.walking = true;
		}
		else if (has("stop")) p.walking = false;
		else if (has("face")) p.heading = float(num(m, "h", p.heading));
		else if (has("view")) p.view = int(num(m, "mode", 1));
		else if (has("look")) { p.relHeading = float(num(m, "heading", 0)); p.relPitch = float(num(m, "pitch", 0)); }
	}

	LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
	{
		if (m == WM_DESTROY)
		{
			PostQuitMessage(0);
			return 0;
		}
		return DefWindowProcW(h, m, w, l);
	}
}

int main(int argc, char **argv)
{
	const double seconds = argc > 1 ? std::atof(argv[1]) : 20.0;
	const bool shake = argc > 2 && std::atoi(argv[2]) != 0; // fast camera swings (~235 deg/s) to show latency
	WNDCLASSW wc = {};
	wc.lpfnWndProc = wndproc;
	wc.hInstance = GetModuleHandleW(nullptr);
	wc.lpszClassName = L"FakeGTA";
	RegisterClassW(&wc);
	RECT rc = {0, 0, kWidth, kHeight};
	AdjustWindowRect(&rc, WS_OVERLAPPEDWINDOW, FALSE);
	HWND hwnd = CreateWindowW(L"FakeGTA", L"Fake GTA (passthrough test)", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 40, 40,
		rc.right - rc.left, rc.bottom - rc.top, nullptr, nullptr, wc.hInstance, nullptr);

	DXGI_SWAP_CHAIN_DESC sd = {};
	sd.BufferCount = 2;
	sd.BufferDesc.Width = kWidth;
	sd.BufferDesc.Height = kHeight;
	sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
	sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
	sd.OutputWindow = hwnd;
	sd.SampleDesc.Count = 1;
	sd.Windowed = TRUE;
	sd.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
	ID3D11Device *dev = nullptr;
	ID3D11DeviceContext *ctx = nullptr;
	IDXGISwapChain *swap = nullptr;
	if (FAILED(D3D11CreateDeviceAndSwapChain(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION, &sd, &swap, &dev, nullptr, &ctx)))
	{
		std::puts("D3D11 init failed");
		return 1;
	}
	std::printf("compositor registered with ReShade: %s\n", compositor::try_register(GetModuleHandleW(nullptr)) ? "yes" : "no (is dxgi.dll ReShade?)");

	ID3D11Texture2D *back = nullptr;
	swap->GetBuffer(0, __uuidof(ID3D11Texture2D), reinterpret_cast<void **>(&back));
	ID3D11RenderTargetView *rtv = nullptr;
	dev->CreateRenderTargetView(back, nullptr, &rtv);
	D3D11_TEXTURE2D_DESC dd = {};
	dd.Width = kWidth;
	dd.Height = kHeight;
	dd.MipLevels = 1;
	dd.ArraySize = 1;
	dd.Format = DXGI_FORMAT_D32_FLOAT;
	dd.SampleDesc.Count = 1;
	dd.BindFlags = D3D11_BIND_DEPTH_STENCIL;
	ID3D11Texture2D *depth = nullptr;
	dev->CreateTexture2D(&dd, nullptr, &depth);
	ID3D11DepthStencilView *dsv = nullptr;
	dev->CreateDepthStencilView(depth, nullptr, &dsv);
	D3D11_DEPTH_STENCIL_DESC dsd = {};
	dsd.DepthEnable = TRUE;
	dsd.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ALL;
	dsd.DepthFunc = D3D11_COMPARISON_GREATER; // reversed Z
	ID3D11DepthStencilState *dss = nullptr;
	dev->CreateDepthStencilState(&dsd, &dss);
	D3D11_RASTERIZER_DESC rd = {};
	rd.FillMode = D3D11_FILL_SOLID;
	rd.CullMode = D3D11_CULL_NONE;
	rd.DepthClipEnable = TRUE;
	ID3D11RasterizerState *rs = nullptr;
	dev->CreateRasterizerState(&rd, &rs);

	ID3DBlob *vsb = nullptr, *psb = nullptr, *err = nullptr;
	if (FAILED(D3DCompile(kShader, std::strlen(kShader), nullptr, nullptr, nullptr, "vs", "vs_5_0", 0, 0, &vsb, &err)) ||
		FAILED(D3DCompile(kShader, std::strlen(kShader), nullptr, nullptr, nullptr, "ps", "ps_5_0", 0, 0, &psb, &err)))
	{
		std::printf("shader: %s\n", err ? static_cast<const char *>(err->GetBufferPointer()) : "?");
		return 1;
	}
	ID3D11VertexShader *vs = nullptr;
	ID3D11PixelShader *ps = nullptr;
	dev->CreateVertexShader(vsb->GetBufferPointer(), vsb->GetBufferSize(), nullptr, &vs);
	dev->CreatePixelShader(psb->GetBufferPointer(), psb->GetBufferSize(), nullptr, &ps);
	const D3D11_INPUT_ELEMENT_DESC layout[] = {
		{"POSITION", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, 0, D3D11_INPUT_PER_VERTEX_DATA, 0},
		{"COLOR", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, 12, D3D11_INPUT_PER_VERTEX_DATA, 0},
		{"CHECKER", 0, DXGI_FORMAT_R32_FLOAT, 0, 24, D3D11_INPUT_PER_VERTEX_DATA, 0},
	};
	ID3D11InputLayout *il = nullptr;
	dev->CreateInputLayout(layout, 3, vsb->GetBufferPointer(), vsb->GetBufferSize(), &il);

	// The scene, in GTA coordinates: ground at kGroundZ, a red pillar, a blue slab near the Minecraft blocks.
	std::vector<Vertex> verts;
	const float g = 150.0f;
	const float quad[6][2] = {{-g, -g}, {g, -g}, {g, g}, {-g, -g}, {g, g}, {-g, g}};
	for (const auto &q : quad)
		verts.push_back({q[0], q[1], kGroundZ, 0, 0, 0, 1});
	add_box(verts, -3, -6, kGroundZ, -2, -5, kGroundZ + 3, 0.85f, 0.15f, 0.1f);   // Minecraft (-3..-2, *, 5..6)
	add_box(verts, 3, -9.5f, kGroundZ, 5, -9, kGroundZ + 1.5f, 0.2f, 0.35f, 0.9f);  // a low wall
	// where the Minecraft blocks are: the diamond pillar (0, 64..66, 6) and the TNT (2, 64, 6); MC z -> GTA -y
	add_edges(verts, 0, -7, kGroundZ, 1, -6, kGroundZ + 3);
	add_edges(verts, 2, -7, kGroundZ, 3, -6, kGroundZ + 1);
	D3D11_BUFFER_DESC bd = {};
	bd.ByteWidth = UINT(verts.size() * sizeof(Vertex));
	bd.BindFlags = D3D11_BIND_VERTEX_BUFFER;
	D3D11_SUBRESOURCE_DATA init = {verts.data()};
	ID3D11Buffer *vb = nullptr;
	dev->CreateBuffer(&bd, &init, &vb);
	D3D11_BUFFER_DESC cbd = {};
	cbd.ByteWidth = sizeof(Mat);
	cbd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
	cbd.Usage = D3D11_USAGE_DYNAMIC;
	cbd.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
	ID3D11Buffer *cb = nullptr;
	dev->CreateBuffer(&cbd, nullptr, &cb);

	WsClient ws;
	ws.start("127.0.0.1", 25599);
	int generation = -1;
	bool scripted = false; // true once a director op arrives: the camera follows the stand-in player
	const auto t0 = std::chrono::steady_clock::now();
	int frame = 0;
	MSG msg = {};
	while (msg.message != WM_QUIT)
	{
		while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE))
		{
			TranslateMessage(&msg);
			DispatchMessageW(&msg);
		}
		const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
		if (t > seconds)
			break;
		++frame;
		compositor::try_register(GetModuleHandleW(nullptr));
		compositor::set_active(ws.connected());
		compositor::set_host_planes(kNear, kFar);

		// Orbit the Minecraft blocks (around Minecraft (0.5, 64, 6.5) = GTA (0.5, -6.5, 63.6)), unless directed.
		float eye[3], yaw, pitch;
		if (!scripted)
		{
			const float a = float(t * 0.45);
			eye[0] = 0.5f + 7.5f * std::sin(a); eye[1] = -6.5f - 7.5f * std::cos(a); eye[2] = kGroundZ + 2.6f + 0.8f * std::sin(a * 0.7f);
			const float dx = 0.5f - eye[0], dy = -6.5f - eye[1], dz = kGroundZ + 1.0f - eye[2];
			yaw = std::atan2(-dx, dy) * 57.29578f + (shake ? 25.0f * std::sin(float(t) * 9.42f) : 0.0f); // GTA: 0 = +y, 90 = -x
			pitch = std::atan2(dz, std::sqrt(dx * dx + dy * dy)) * 57.29578f;
		}
		else
		{
			Player &pl = g_player;
			if (pl.walking)
			{
				const float wx = pl.tx - pl.x, wy = pl.ty - pl.y, dist = std::sqrt(wx * wx + wy * wy);
				const float step = pl.speed / 60.0f;
				if (dist <= step) { pl.x = pl.tx; pl.y = pl.ty; pl.walking = false; }
				else { pl.x += wx / dist * step; pl.y += wy / dist * step; pl.heading = std::atan2(-wx, wy) * 57.29578f; }
			}
			yaw = pl.heading + pl.relHeading;
			pitch = pl.relPitch;
			const float d2r = 3.14159265f / 180.0f;
			if (pl.view == 4) { eye[0] = pl.x; eye[1] = pl.y; eye[2] = pl.z + 0.65f; }
			else
			{
				// third person: 3.5 m behind along the camera direction, a little up and to the right
				const float fx = -std::sin(yaw * d2r) * std::cos(pitch * d2r), fy = std::cos(yaw * d2r) * std::cos(pitch * d2r), fz = std::sin(pitch * d2r);
				eye[0] = pl.x - fx * 3.5f + std::cos(yaw * d2r) * 0.4f; eye[1] = pl.y - fy * 3.5f + std::sin(yaw * d2r) * 0.4f; eye[2] = pl.z + 0.7f - fz * 3.5f;
			}
		}

		if (ws.connected())
		{
			if (ws.generation() != generation)
			{
				generation = ws.generation();
				char v[128];
				snprintf(v, sizeof(v), "{\"t\":\"view\",\"w\":%d,\"h\":%d}", kWidth, kHeight);
				ws.send(v);
				std::string cols;
				for (int x = -30; x <= 30; ++x)
					for (int z = -30; z <= 30; ++z)
						cols += (cols.empty() ? "" : ",") + std::to_string(x) + "," + std::to_string(z) + ",62,63";
				ws.send("{\"t\":\"ground\",\"c\":[" + cols + "]}");
				for (const char *c : {"fill -30 64 -30 30 80 30 minecraft:air", "fill 0 64 6 0 66 6 minecraft:diamond_block",
						 "setblock 2 64 6 minecraft:tnt", "setblock 2 64 8 minecraft:glass", "fill -1 64 9 1 64 9 minecraft:oak_planks",
						 "setblock -2 64 3 minecraft:grass_block", "setblock 4 64 10 minecraft:gold_block"})
					ws.send(std::string("{\"t\":\"cmd\",\"c\":\"") + c + "\"}");
			}
			// the same conversion as the GTA script: MC = (x, z + yOffset, -y), yaw = 180 - heading, pitch = -pitch
			float mcYaw = std::fmod(180.0f - yaw + 540.0f, 360.0f) - 180.0f;
			compositor::set_host_pose(mcYaw, -pitch, 0.0f, kFov, eye[0], eye[2] + kYOffset, -eye[1]);
			char buf[512];
			const Player &pl = g_player;
			const bool fp = !scripted || pl.view == 4;
			const float body = std::fmod(180.0f - pl.heading + 540.0f, 360.0f) - 180.0f;
			snprintf(buf, sizeof(buf), "{\"t\":\"cam\",\"f\":%d,\"p\":[%.4f,%.4f,%.4f],\"r\":[%.3f,%.3f,0],\"fov\":%.2f,\"fp\":%s,\"pl\":[%.4f,%.4f,%.4f],\"h\":%.3f}",
				frame, eye[0], eye[2] + kYOffset, -eye[1], mcYaw, -pitch, kFov, fp ? "true" : "false", pl.x, pl.z - 1.0f + kYOffset, -pl.y, body);
			ws.send(buf);
			std::string m;
			while (ws.poll(m))
			{
				if (compact(m).find("\"t\":\"gta\"") != std::string::npos)
				{
					scripted = true;
					director_op(m);
				}
				else if (m.find("explosion") != std::string::npos)
					std::printf("event: %s\n", m.c_str());
			}
		}

		const Mat vp = view_proj(eye, pitch, yaw, kFov, float(kWidth) / kHeight);
		D3D11_MAPPED_SUBRESOURCE mapped;
		ctx->Map(cb, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped);
		// HLSL float4x4 in a cbuffer is column-major by default: upload the transpose of our row-major matrix
		Mat tr;
		for (int i = 0; i < 4; ++i)
			for (int j = 0; j < 4; ++j)
				tr.m[i][j] = vp.m[j][i];
		std::memcpy(mapped.pData, &tr, sizeof(Mat));
		ctx->Unmap(cb, 0);

		const float sky[4] = {0.55f, 0.7f, 0.92f, 1.0f};
		ctx->ClearRenderTargetView(rtv, sky);
		ctx->ClearDepthStencilView(dsv, D3D11_CLEAR_DEPTH, 0.0f, 0);
		ctx->OMSetRenderTargets(1, &rtv, dsv);
		ctx->OMSetDepthStencilState(dss, 0);
		ctx->RSSetState(rs);
		D3D11_VIEWPORT vpd = {0, 0, float(kWidth), float(kHeight), 0, 1};
		ctx->RSSetViewports(1, &vpd);
		const UINT stride = sizeof(Vertex), offset = 0;
		ctx->IASetVertexBuffers(0, 1, &vb, &stride, &offset);
		ctx->IASetInputLayout(il);
		ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
		ctx->VSSetShader(vs, nullptr, 0);
		ctx->VSSetConstantBuffers(0, 1, &cb);
		ctx->PSSetShader(ps, nullptr, 0);
		ctx->Draw(UINT(verts.size()), 0);
		swap->Present(1, 0);
	}
	ws.stop();
	return 0;
}
