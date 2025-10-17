"""Simple WebSocket connection test"""
import socket

def test_port_open(host='localhost', port=3500):
    """Test if port is open and accepting connections"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"✅ Port {port} on {host} is OPEN and accessible")
            return True
        else:
            print(f"❌ Port {port} on {host} is CLOSED (error code: {result})")
            return False
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing browser WebSocket port accessibility...")
    success = test_port_open()
    exit(0 if success else 1)
