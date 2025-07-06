from http.server import HTTPServer
import os
import sys
import threading

install_dir = os.environ.get('CEREBELLA_INSTALL_DIR', os.path.dirname(os.path.abspath(__file__)))
if install_dir not in sys.path:
    sys.path.insert(0, install_dir)

from cerebella_server import CerebellaLocalServer, CEREBELLA_SERVER_PORT, watch_files_loop, compute_state_vector_loop


def main():
    # Check if embeddings are enabled
    enable_embeddings = '--embeddings' in sys.argv
    
    print(f"Server starting on http://localhost:{CEREBELLA_SERVER_PORT}")

    watch_thread = threading.Thread(target=watch_files_loop, daemon=True)
    watch_thread.start()
    
    if enable_embeddings:
        embedding_thread = threading.Thread(target=compute_state_vector_loop, daemon=True)
        embedding_thread.start()
    try:
        httpd = HTTPServer(('localhost', CEREBELLA_SERVER_PORT), CerebellaLocalServer)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(e)


if __name__ == '__main__':
    main()