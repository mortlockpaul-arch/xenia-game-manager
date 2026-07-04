import socket

def wake_on_lan(mac):
    mac = mac.replace(":", "").replace("-", "")
    packet = bytes.fromhex("FF" * 6 + mac * 16)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.sendto(packet, ("192.168.0.19", 9))
    sock.close()

wake_on_lan("14:4F:8A:35:88:F6")