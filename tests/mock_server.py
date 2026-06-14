from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import sys
import threading
import time

class MockUniversityLMSHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Override to suppress console logging output
        return

    def _get_cookie(self, cookie_name):
        cookie_header = self.headers.get('Cookie')
        if not cookie_header:
            return None
        cookies = dict(item.split('=', 1) for item in cookie_header.split('; ') if '=' in item)
        return cookies.get(cookie_name)

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == "/login":
            # Serve login form
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
            <html>
                <body>
                    <h2>CAS Login</h2>
                    <form action="/login" method="POST">
                        Username: <input type="text" id="username" name="username"><br>
                        Password: <input type="password" id="password" name="password"><br>
                        <input type="submit" id="submit-btn" value="Login">
                    </form>
                </body>
            </html>
            """)
            
        elif parsed_path.path == "/dashboard":
            # Verify session cookie
            token = self._get_cookie("session_token")
            if token == "valid_token":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                
                # Check for dynamic changes using a simple file or memory store (global var)
                announcement_content = getattr(sys.modules[__name__], "announcement_text", "Initial announcement: No classes next Monday!")
                
                self.wfile.write(f"""
                <html>
                    <body>
                        <div id="dashboard-main">
                            <h1>Welcome to the LMS Dashboard</h1>
                            <div id="announcements-sec">
                                <h2>Announcements</h2>
                                <p class="timestamp">Last updated: {time.strftime('%H:%M:%S')}</p>
                                <div class="announcement-content">{announcement_content}</div>
                            </div>
                        </div>
                    </body>
                </html>
                """.encode("utf-8"))
            else:
                # Redirect back to login
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == "/login":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(post_data)
            
            username = params.get('username', [None])[0]
            password = params.get('password', [None])[0]
            
            if username == "student_user" and password == "secure_password_123":
                # Success! Set session cookie and redirect to dashboard
                self.send_response(302)
                self.send_header("Location", "/dashboard")
                self.send_header("Set-Cookie", "session_token=valid_token; Path=/; HttpOnly")
                self.end_headers()
            else:
                # Failure
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"Invalid credentials. <a href='/login'>Try again</a>")

def run_server(port=8080):
    server = HTTPServer(('localhost', port), MockUniversityLMSHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return server
