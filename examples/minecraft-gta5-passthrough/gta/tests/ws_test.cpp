// Checks the plugin's WebSocket client against the running Minecraft mod: handshake, masked frames both
// ways, a 60 Hz camera stream, ground columns, a command, and the explosion event coming back.
#include "../src/ws.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <string>
#include <thread>

int main()
{
	WsClient ws;
	ws.start("127.0.0.1", 25599);
	for (int i = 0; i < 50 && !ws.connected(); ++i)
		std::this_thread::sleep_for(std::chrono::milliseconds(100));
	if (!ws.connected())
	{
		std::puts("not connected");
		return 1;
	}
	std::puts("connected");
	std::string cols;
	for (int x = -12; x <= 12; ++x)
		for (int z = -12; z <= 12; ++z)
			cols += (cols.empty() ? "" : ",") + std::to_string(x) + "," + std::to_string(z) + ",62,63";
	ws.send("{\"t\":\"ground\",\"c\":[" + cols + "]}");
	ws.send("{\"t\":\"cmd\",\"c\":\"summon minecraft:tnt 1.5 64 5.5 {fuse:40}\"}");
	int explosions = 0;
	for (int f = 0; f < 60 * 4; ++f)
	{
		char buf[512];
		const double a = f / 60.0;
		snprintf(buf, sizeof(buf), "{\"t\":\"cam\",\"f\":%d,\"p\":[%.3f,66.6,%.3f],\"r\":[%.2f,15,0],\"fov\":60,\"fp\":true}",
			f, 0.5 + 6 * std::sin(a), 5.5 - 6 * std::cos(a), -std::fmod(a * 57.2958, 360.0));
		ws.send(buf);
		std::string m;
		while (ws.poll(m))
		{
			std::printf("recv: %s\n", m.c_str());
			explosions += m.find("explosion") != std::string::npos;
		}
		std::this_thread::sleep_for(std::chrono::milliseconds(16));
	}
	std::printf("explosions: %d\n", explosions);
	ws.stop();
	return explosions > 0 ? 0 : 2;
}
