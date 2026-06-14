# Page Watcher Service

A self-hosted, Dockerized daemon service that monitors web pages and JSON APIs (even those hidden behind Single Sign-On / Central Authentication Service portals), tracks changes, and pushes rich Discord notifications containing clean text diffs and page screenshots.

---

## ✨ Features

- **Central Authentication Service (SSO/CAS) support**: Run sequences of form fills, navigation, and clicks using configuration-based login "recipes".
- **Stealth Scraper**: Built on **Camoufox (Playwright)** to mimic human browser behavior and evade basic anti-scraping systems.
- **API Fetching & Auth Injection**: Monitor JSON endpoints by executing internal fetches directly in the page context.
- **Decoupled Site-Specific Handler Plugins**: Isolate custom authentication queries and DOM traversal logic (e.g., extracting token secrets from hidden HTML inputs) into standalone, user-supplied scripts in the `site_specific/` folder.
- **Sequential Group Locking**: Sequences checks for the same portal (e.g. university groups) using an asynchronous lock to prevent SSO login storms and rate-limiting.
- **Session Persistence**: Stores cookies and storage state in local SQLite databases to maintain long-lived sessions and minimize authentication requests.
- **Rich Notifications**: Formats unified text/JSON diffs and attaches full-page screenshots directly to Discord Webhook embeds.
- **Configurable Screen Capturing**: Configures screenshot-saving globally, per-group, or down to individual pages.

---

## 🛠️ File Structure

```
page-watcher/
├── config.example.yaml    # Template configuration (copy to config.yaml)
├── Dockerfile             # Multi-arch Playwright/Camoufox image definition
├── docker-compose.yml     # Container services and volume mounts
├── requirements.txt       # Python dependencies
├── run_tests.py           # Local test runner
├── src/
│   ├── main.py            # CLI entry point
│   ├── config.py          # Config parsing & Pydantic validation
│   ├── database.py        # SQLite interactions (cookies, history, and states)
│   ├── parser.py          # HTML cleaning & unified diff builder
│   ├── browser.py         # Browser engine and dynamic plugin loader
│   ├── notifier.py        # Discord webhook poster
│   └── handlers.py        # Default generic API fetch handlers
├── site_specific/         # Dedicated directory for custom site handler scripts
│   └── MyBK_app/
│       ├── README.md      # Details about MyBK's hidden inputs and login redirects
│       └── handler.py     # Custom fetch script containing `async def fetch_api(page, api_url)`
└── tests/                 # Unit and integration test suites
```

---

## 🚀 Getting Started

### 1. Requirements
Ensure you have the following installed:
* [Docker](https://docs.docker.com/get-docker/)
* [Docker Compose](https://docs.docker.com/compose/install/)

### 2. Configuration
Copy the template configuration file:
```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` on your host machine to fill in:
* Your Discord Webhook URL.
* Page URLs, CSS selectors, and SSO credentials.

#### Example Config:
```yaml
discord_webhook_url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"
check_interval_seconds: 180

groups:
  MyBK:
    name: "HCMUT MyBK"
    api_handler: "site_specific/MyBK_app/handler.py"
    login:
      type: "recipe"
      recipe:
        - action: "navigate"
          url: "http://sso.hcmut.edu.vn/cas/login?service=https%3A%2F%2Fmybk.hcmut.edu.vn%2Fapp%2Flogin%2Fcas"
        - action: "fill"
          selector: "#username"
          value: "my_username"
        - action: "fill"
          selector: "#password"
          value: "my_password"
        - action: "click"
          selector: "[type='submit']"
        - action: "wait_for_url"
          value: "https://mybk.hcmut.edu.vn/app/**"
    pages:
      - key: "ctxh"
        name: "Social Workdays"
        url: "https://mybk.hcmut.edu.vn/api/v1/student-activities/social-workdays/by-student-code/2310641"
```

---

## 🔌 Site-Specific Plugins (`site_specific/`)

To keep the codebase generic and clean, custom handling for quirky sites is completely decoupled. 

### How to Create a Custom Handler
1. Create a sub-folder under `site_specific/` (e.g. `site_specific/my_site/`).
2. Add a `README.md` detailing the portal's authentication behavior.
3. Write a Python script (e.g. `handler.py`) defining an asynchronous function:
   ```python
   async def fetch_api(page, api_url: str) -> str:
       # Write custom logic to navigate, extract tokens, build headers, and execute fetch
       ...
       return raw_response_text
   ```
4. Reference this script in your `config.yaml` using the `api_handler` field on the group level.

Because `./site_specific` is mounted as a volume in `docker-compose.yml`, you can write and update these handlers dynamically **without rebuilding the container image**.

---

## 🐳 Running the Service

Build and start the daemon container in detached mode:
```bash
docker compose up -d
```

### Viewing Logs
```bash
docker compose logs -f
```

### Stopping the Service
```bash
docker compose down
```

---

## 🧪 Running Tests
Verify that all unit and integration tests (including SSO recipe validation, cookie capture, and diff parsing) pass successfully:

```bash
docker compose run --rm \
  -v ./run_tests.py:/app/run_tests.py:ro \
  -v ./tests:/app/tests:ro \
  page-watcher python run_tests.py
```
