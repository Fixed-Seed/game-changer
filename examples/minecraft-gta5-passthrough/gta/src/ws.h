// A minimal WebSocket client (RFC 6455 text frames) for the link to the Minecraft mod on 127.0.0.1.
// A background thread connects (and reconnects), answers pings and queues received text messages;
// send() may be called from any thread.
#pragma once
#include <atomic>
#include <deque>
#include <mutex>
#include <string>
#include <thread>

class WsClient
{
public:
	void start(const char *host, int port);
	void stop();
	bool connected() const { return m_connected; }
	/// Bumped on every successful (re)connect, so the caller can resend its state.
	int generation() const { return m_generation; }
	bool send(const std::string &text);
	bool poll(std::string &message);

private:
	void run();
	bool open();
	void close();
	bool sendFrame(int opcode, const char *data, size_t size);
	bool recvAll(void *buffer, size_t size);

	std::string m_host;
	int m_port = 0;
	uintptr_t m_socket = ~uintptr_t(0);
	std::atomic<bool> m_connected{false};
	std::atomic<bool> m_stop{false};
	std::atomic<int> m_generation{0};
	std::mutex m_sendLock;
	std::mutex m_queueLock;
	std::deque<std::string> m_queue;
	std::thread m_thread;
	uint32_t m_maskState = 0x9E3779B9u;
};
