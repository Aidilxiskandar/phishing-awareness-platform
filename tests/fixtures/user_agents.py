"""Realistic User-Agent strings for detection tests.

Each entry is (id, user_agent, expected family substring or None). SCANNER_UAS
must never be classified as human; BROWSER_UAS must never be classified as
scanner. When you see a new scanner in the evidence log, add its UA here first
(the test will fail), then add a signature in app/detection.py.

Strings are modelled on what these clients actually send; some vendors (notably
Defender Safe Links, Proofpoint, Mimecast) often use a generic browser UA instead,
which is why IP ranges, timing and the JS beacon exist as well.
"""

SCANNER_UAS = [
    # --- Email security gateways / link protection ---
    ("defender-safelinks", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 ATPSafeLinks/1.0", "Safe Links"),
    ("safelinks-short", "Mozilla/5.0 SafeLinks", "Safe Links"),
    ("ms-office-existence", "Microsoft Office Existence Discovery", "Microsoft Office"),
    ("ms-office-protocol", "Microsoft Office Protocol Discovery", "Microsoft Office"),
    ("ms-outlook-fetch", "Microsoft Office/16.0 (Windows NT 10.0; Microsoft Outlook 16.0.17126; Pro)",
     "Microsoft Office"),
    ("ms-webdav", "Microsoft-WebDAV-MiniRedir/10.0.19045", "Microsoft Office"),
    ("microsoft-preview", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like "
     "Gecko) Chrome/116.0.1938.76 Safari/537.36 Edg/116.0.1938.76 MicrosoftPreview/2.0 "
     "+https://aka.ms/MicrosoftPreview", "Outlook/Teams"),
    ("teams-skype-preview", "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "SkypeUriPreview Preview/0.5 skype-url-preview@microsoft.com", "Outlook/Teams"),
    ("bingpreview", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "BingPreview/1.0b", "Outlook/Teams"),
    ("proofpoint", "Mozilla/5.0 (compatible; Proofpoint URL Defense)", "Proofpoint"),
    ("proofpoint-urldefense", "urldefense-scanner/2.0", "Proofpoint"),
    ("mimecast", "Mozilla/5.0 (compatible; Mimecast URL Protect)", "Mimecast"),
    ("barracuda", "BarracudaCentral/2.0", "Barracuda"),
    ("barracuda-lps", "Mozilla/5.0 (compatible; Barracuda Link Protection)", "Barracuda"),
    ("ironport", "Mozilla/5.0 (compatible; IronPort-WBRS)", "Cisco"),
    ("cisco-secure-email", "Cisco Secure Email URL Scanner/1.0", "Cisco"),
    ("symantec", "Mozilla/5.0 (compatible; Symantec Click-time URL Protection)", "Symantec"),
    ("trendmicro", "Mozilla/5.0 (compatible; TrendMicro Web Reputation)", "Trend Micro"),
    ("fortiguard", "FortiGuard-URL-Rating/1.0", "Fortinet"),
    ("virustotal", "Mozilla/5.0 (compatible; VirusTotal-Scanner)", "VirusTotal"),
    # --- Google ---
    ("gmail-image-proxy", "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 "
     "(via ggpht.com GoogleImageProxy)", "Google"),
    ("google-safety", "Google-Safety", "Google"),
    ("googlebot", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "Google"),
    ("google-inspection", "Mozilla/5.0 (compatible; Google-InspectionTool/1.0)", "Google"),
    ("yahoo-proxy", "YahooMailProxy; https://help.yahoo.com/kb/yahoo-mail-proxy-SLN28749.html",
     "Yahoo"),
    # --- Chat / social link-preview bots ---
    ("slackbot", "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)", "Slack"),
    ("slack-imgproxy", "Slack-ImgProxy (+https://api.slack.com/robots)", "Slack"),
    ("whatsapp", "WhatsApp/2.23.20.0 A", "WhatsApp"),
    ("whatsapp-ios", "WhatsApp/2.24.6.77 i", "WhatsApp"),
    ("telegram", "TelegramBot (like TwitterBot)", "Telegram"),
    ("linkedin", "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)",
     "LinkedIn"),
    ("facebook", "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
     "Facebook"),
    ("imessage-preview", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_1) AppleWebKit/601.2.4 (KHTML, "
     "like Gecko) Version/9.0.1 Safari/601.2.4 facebookexternalhit/1.1 Facebot Twitterbot/1.0",
     "Facebook"),
    ("meta-agent", "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)",
     "Facebook"),
    ("twitterbot", "Twitterbot/1.0", "Twitter"),
    ("discordbot", "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)", "Discord"),
    # --- Crawlers ---
    ("bingbot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; "
     "+http://www.bing.com/bingbot.htm) Chrome/116.0.1938.76 Safari/537.36", "crawler"),
    ("applebot", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like "
     "Gecko) Version/17.4 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)",
     "crawler"),
    # --- Headless / automated browsers ---
    ("headless-chrome", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "HeadlessChrome/124.0.6367.60 Safari/537.36", "Headless Chrome"),
    ("headless-chrome-win", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like "
     "Gecko) HeadlessChrome/131.0.0.0 Safari/537.36", "Headless Chrome"),
    ("phantomjs", "Mozilla/5.0 (Unknown; Linux x86_64) AppleWebKit/538.1 (KHTML, like Gecko) "
     "PhantomJS/2.1.1 Safari/538.1", "PhantomJS"),
    ("puppeteer", "Mozilla/5.0 (X11; Linux x86_64) Puppeteer/22.0.0", "Puppeteer"),
    ("playwright", "Mozilla/5.0 (X11; Linux x86_64) Playwright/1.44", "Puppeteer"),
    ("selenium", "Mozilla/5.0 Selenium WebDriver", "Puppeteer"),
    ("lighthouse", "Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like "
     "Gecko) Chrome/119.0.0.0 Mobile Safari/537.36 Chrome-Lighthouse", "headless"),
    # --- HTTP libraries / CLI tools ---
    ("python-requests", "python-requests/2.32.3", "python-requests"),
    ("python-urllib", "Python-urllib/3.12", "Python"),
    ("httpx", "python-httpx/0.27.0", "Python"),
    ("aiohttp", "Python/3.12 aiohttp/3.9.5", "Python"),
    ("go", "Go-http-client/2.0", "Go-http-client"),
    ("curl", "curl/8.4.0", "curl"),
    ("wget", "Wget/1.21.4", "Wget"),
    ("okhttp", "okhttp/4.12.0", "OkHttp"),
    ("java", "Java/17.0.10", "Java"),
    ("java-httpclient", "Java-http-client/21.0.2", "Java"),
    ("apache-httpclient", "Apache-HttpClient/4.5.14 (Java/17.0.10)", "Java"),
    ("axios", "axios/1.7.2", "Node.js"),
    ("node-fetch", "node-fetch/1.0 (+https://github.com/bitinn/node-fetch)", "Node.js"),
    ("undici", "undici", "Node.js"),
    ("perl", "libwww-perl/6.72", "scripting"),
    ("scrapy", "Scrapy/2.11.2 (+https://scrapy.org)", "scripting"),
    ("postman", "PostmanRuntime/7.39.0", "scripting"),
    ("powershell", "Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.19041.4648",
     "scripting"),
]

BROWSER_UAS = [
    ("chrome-windows", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/131.0.0.0 Safari/537.36"),
    ("chrome-mac", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/131.0.0.0 Safari/537.36"),
    ("chrome-linux", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/131.0.0.0 Safari/537.36"),
    ("chrome-android", "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/131.0.0.0 Mobile Safari/537.36"),
    ("chrome-android-samsung-device", "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36"),
    ("chrome-ios", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, "
     "like Gecko) CriOS/131.0.6778.73 Mobile/15E148 Safari/604.1"),
    ("edge-windows", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"),
    ("edge-android", "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/131.0.0.0 Mobile Safari/537.36 EdgA/131.0.0.0"),
    ("edge-ios", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, "
     "like Gecko) Version/17.0 EdgiOS/131.2903.68 Mobile/15E148 Safari/605.1.15"),
    ("ie11-legacy", "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko"),
    ("firefox-windows", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"),
    ("firefox-linux", "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0"),
    ("firefox-ios", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, "
     "like Gecko) FxiOS/133.0 Mobile/15E148 Safari/605.1.15"),
    ("safari-mac", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like "
     "Gecko) Version/18.1 Safari/605.1.15"),
    ("safari-iphone", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"),
    ("safari-ipad", "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like "
     "Gecko) Version/17.5 Mobile/15E148 Safari/604.1"),
    ("samsung-internet", "Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-S918B) AppleWebKit/537.36 (KHTML, "
     "like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36"),
    ("opera", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/130.0.0.0 Safari/537.36 OPR/115.0.0.0"),
    ("yandex-browser", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/128.0.0.0 YaBrowser/24.10.0.0 Safari/537.36"),
    # In-app browsers: what a person gets when they tap a link inside an app.
    ("outlook-ios-inapp", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Mobile/15E148"),
    ("outlook-android-webview", "Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/AP2A.240805.005; wv) "
     "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0.6668.100 Mobile Safari/537.36"),
    ("new-outlook-webview2", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like "
     "Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0 OneOutlook/1.2024.1106.100"),
    ("gmail-ios-inapp", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) GSA/336.0.700721794 Mobile/15E148 Safari/604.1"),
    ("facebook-inapp", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/470.0.0.37.106;FBBV/625000000;FBDV/iPhone15,2;"
     "FBMD/iPhone;FBSN/iOS;FBSV/17.5;FBSS/3;FBCR/;FBID/phone;FBLC/en_US;FBOP/80]"),
    ("linkedin-inapp", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Mobile/15E148 [LinkedInApp]/9.30.1453"),
    ("line-inapp", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, "
     "like Gecko) Mobile/15E148 Safari Line/14.7.0"),
    ("teams-desktop", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0 Teams/24295.605.3225.8804/49"),
    ("brave", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/131.0.0.0 Safari/537.36"),
]
