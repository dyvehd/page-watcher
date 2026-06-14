# MyBK Custom API Authentication Handler

## Target URLs
* Dashboard SPA: `https://mybk.hcmut.edu.vn/app/`
* API Endpoints: `https://mybk.hcmut.edu.vn/api/v1/...`

## Why Custom Logic is Needed
The HCMUT MyBK application is a hybrid legacy-SPA system.
1. The CAS SSO authentication redirects to the `/app/login/cas` endpoint, which validates the ticket and renders a hidden DOM input field containing the JWT token:
   ```html
   <input type="hidden" id="hid_Token" value="eyJhbGciOiJIUzUx..."/>
   ```
2. The site does not store the JWT token in standard browser client storage (like `localStorage` or `sessionStorage`), nor does it use standard script-accessible cookies. The frontend SPA reads this value directly from the DOM on startup.
3. Therefore, standard token-scraping logic (which only inspects client storage) fails to authenticate, resulting in `403 Forbidden` API responses.

## Handler Behavior
The handler:
1. Navigates the browser to the MyBK SPA context (`https://mybk.hcmut.edu.vn/app/`).
2. Scans the DOM for the hidden `#hid_Token` input (and falls back to scanning other input tags).
3. Injects the retrieved token into the request's `Authorization: Bearer <token>` header.
4. Executes the `fetch` request directly inside the authenticated browser context to bypass CORS and session limits.
