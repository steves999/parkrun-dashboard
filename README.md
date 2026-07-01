# Steve's Parkrun Dashboard

Auto-updating dashboard hosted on GitHub Pages.  
Scrapes parkrun.co.nz every Sunday and regenerates `index.html` automatically.

---

## One-time setup (15 minutes, all in browser)

### 1 — Create the GitHub repo

1. Go to [github.com/new](https://github.com/new)
2. Owner: `steves999` · Name: `parkrun-dashboard`
3. Set to **Public** (required for free GitHub Pages)
4. Tick **Add a README file**
5. Click **Create repository**

---

### 2 — Upload the files

In your new repo, click **Add file → Upload files** and upload:
- `generate.py`
- `README.md` (replace the default one)

Then create the workflow file manually:
1. Click **Add file → Create new file**
2. Name it exactly: `.github/workflows/update.yml`
3. Paste the contents of `update.yml` from this package
4. Click **Commit changes**

---

### 3 — Get your parkrun session cookie

Parkrun requires you to be logged in. Here's how to grab your cookie:

1. Open **Chrome** and go to [parkrun.co.nz](https://www.parkrun.co.nz)
2. Log in to your account
3. Press **F12** to open DevTools
4. Click the **Application** tab (top menu)
5. In the left sidebar: **Storage → Cookies → https://www.parkrun.co.nz**
6. Look through the cookie list and copy the **entire row values** for:
   - `parkrun_user` (the most important one)
   - Any cookie named `__session`, `PHPSESSID`, or similar session cookie
7. Format them as: `parkrun_user=VALUE; __session=OTHERVALUE`

---

### 4 — Add the cookie as a GitHub Secret

1. In your repo, go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `PARKRUN_COOKIE`
4. Value: the cookie string from step 3
5. Click **Add secret**

---

### 5 — Enable GitHub Pages

1. In your repo, go to **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` · Folder: `/ (root)`
4. Click **Save**

---

### 6 — Run it for the first time

1. Go to **Actions** tab in your repo
2. Click **Update Parkrun Dashboard** in the left list
3. Click **Run workflow → Run workflow**
4. Watch it run (takes ~30 seconds)
5. After it finishes, your dashboard is live at:
   `https://steves999.github.io/parkrun-dashboard/`

---

## After each Saturday parkrun

Nothing to do — it runs automatically every Sunday morning at 10am NZT.

If you want to update it immediately after a run, just go to **Actions → Run workflow**.

---

## Cookie expiry

Parkrun cookies last several weeks. When the Action starts failing (you'll get
an email from GitHub), just repeat step 3–4 above with a fresh cookie.

---

## Adding new events to the tourist map

Edit `EVENT_COUNTRY_MAP` in `generate.py`. The key is the event URL slug —
lowercase, no spaces. Find it in the parkrun event URL:
`parkrun.co.nz/cornwallpark/` → slug is `cornwallpark`

For Australian events in 2027, add them as `"sydneyolympicpark": "AU"` etc.
