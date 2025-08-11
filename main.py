from http.server import HTTPServer
import os
import sys
import threading

install_dir = os.environ.get('CEREBELLA_INSTALL_DIR', os.path.dirname(os.path.abspath(__file__)))
if install_dir not in sys.path:
    sys.path.insert(0, install_dir)

from cerebella_server import CerebellaLocalServer, CEREBELLA_SERVER_PORT, watch_files_loop


def main():
    print(f"Server starting on http://localhost:{CEREBELLA_SERVER_PORT}")

    watch_thread = threading.Thread(target=watch_files_loop, daemon=True)
    watch_thread.start()
    
    try:
        httpd = HTTPServer(('localhost', CEREBELLA_SERVER_PORT), CerebellaLocalServer)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(e)


if __name__ == '__main__':
    main()