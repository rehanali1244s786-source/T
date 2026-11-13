"""
i18n.py - English, Urdu, and Hindi translations and lookup helpers L() and tr().
"""

from __future__ import annotations

from typing import Dict

from db import db

LANG_NAMES: Dict[str, str] = {
    "en": "English 🇬🇧",
    "ur": "اردو 🇵🇰",
    "hi": "हिन्दी 🇮🇳",
}

NEW_HELP: str = (
    "\n✨ <b>More</b>\n"
    "📋 <code>/menu</code> — interactive command &amp; action menu\n"
    "🎤 <code>/artist Karan Aujla</code> — artist page, albums &amp; top songs\n"
    "ℹ️ <b>Info</b> button on every song — album, year, genre, BPM, key\n"
    "🔗 <b>Share</b> button — a card with a link that opens the song\n"
    "🔔 <code>/follow artist</code> · /following — get notified about new releases\n"
    "🎁 /invite — invite friends, earn more daily recognitions\n"
    "⭐ /premium — priority downloads &amp; more\n"
    "🏷 <code>/brand text</code> — custom footer for your group (premium)"
)

STR: Dict[str, Dict[str, str]] = {
    "en": {
        "rec_usage": "🎧 <b>Song recognition</b>\n\nSend me a <b>voice note</b>, audio, or video clip — or reply to one with /find — and I'll tell you the song.",
        "rec_listening": "🎧 <b>Listening…</b>\nIdentifying the song, please wait.",
        "rec_found": "✅ <b>Song found!</b>\n\n🎶 <b>{title}</b>\n👤 {artist}{album}\n\n👇 Download it below:",
        "rec_none": "😕 <b>I couldn't recognize this song.</b>\nTry a clearer clip (10–20 seconds with the music loud).",
        "rec_fail": "❌ Recognition is not working right now. Please try again later.",
        "rec_limit": "⏳ Daily limit reached (<b>{n}</b> recognitions per day). Try again tomorrow.",
        "rec_big": "❌ File is too big. Send a clip under 20 MB.",
        "rec_help": "🎧 /find — reply to a voice/audio/video to identify the song (or just send it in private chat)",
        "join_text": "🔒 <b>Join Required</b>\n\nTo use this bot, please join the channel(s)/group(s) below,\nthen tap <b>✅ I've Joined</b>.",
        "join_btn": "Join {title}",
        "join_done": "✅ I've Joined",
        "join_not_yet": "❌ You haven't joined everything yet!",
        "join_first": "🔒 Join required first",
        "join_ok": "✅ <b>Verified!</b>\n\nSend me a song name or use /song to start 🎧",
        "join_verified": "✅ Verified!",
        "banned": "🚫 You are banned from using this bot.",
        "maintenance": "🛠 <b>Maintenance Mode</b>\n\nThe bot is currently undergoing maintenance. Please try again shortly.",
        "start": (
            "🎧 <b>Music &amp; Video Downloader</b>\n\nHey <b>{name}</b>! 👋\n"
            "Send me a <b>song name</b> or a <b>YouTube link</b> and I'll get it as:\n\n"
            "🎵 <b>Audio</b> — high quality\n🎬 <b>Video</b> — 480p\n\n"
            "⚡ <b>Quick commands</b>\n<code>/song Tum Hi Ho a</code> → 🎵 audio\n"
            "<code>/song Tum Hi Ho v</code> → 🎬 video (480p)\n\n"
            "✨ <i>Or just type a name to pick from a list.</i>"
        ),
        "help": (
            "📖 <b>How to use</b>\n\n"
            "🎵 <code>/song Tum Hi Ho a</code> — get the <b>audio</b>\n"
            "🎬 <code>/song Tum Hi Ho v</code> — get the <b>video</b> (always 480p)\n"
            "<b>A</b> = Audio · <b>V</b> = Video\n\n"
            "🔎 <code>/search Tum Hi Ho</code> — pick from a results list\n"
            "🎤 <code>/lyrics Tum Hi Ho</code> — song lyrics\n"
            "📊 /stats — bot statistics\n🌐 /lang — change language\n"
            "🔍 Inline: type <code>@{bot} song name</code> in any chat\n\n"
            "💡 Without <b>a</b>/<b>v</b> I show a list to pick from.\n"
            "🔗 You can also paste a YouTube link.\n📦 Max upload size: 50 MB."
        ),
        "search_usage": "🔎 Send the song name too.\n<code>/search On Top Karan Aujla</code>",
        "song_usage": "🎵 Send the song name too.\n<b>Audio:</b> <code>/song DXB Karan Aujla a</code>\n<b>Video:</b> <code>/song DXB Karan Aujla v</code>",
        "fetching": "⏳ <b>Fetching info…</b>",
        "bad_link": "❌ Couldn't read that link. Try again later.",
        "load_failed": "❌ Couldn't load that video. Search again.",
        "searching": "🔎 <b>Searching…</b>\n<i>{q}</i>",
        "search_failed": "❌ <b>Search failed.</b>\n{hint}",
        "no_results": "😕 <b>No results found.</b>\nTry adding the artist name.",
        "results_title": "🔎 <b>Results for</b> <i>{q}</i>\n",
        "tap": "\n👇 <i>Tap a button or number to choose</i>",
        "choose": "👇 <b>Choose a format</b>",
        "views": "views",
        "btn_audio": "🎵 Audio",
        "btn_video": "🎬 Video 480p",
        "btn_lyrics": "🎤 Lyrics",
        "label_audio": "🎵 Audio",
        "label_video": "🎬 Video 480p",
        "downloading": "⏬ <b>Downloading…</b>\n{label}\n<i>{title}</i>",
        "uploading": "⬆️ <b>Uploading…</b>\n{label}",
        "queue": "⏳ <b>You're #{n} in line</b>\n<i>{title}</i>\nThe server is busy — I'll start as soon as it's your turn.",
        "too_long": "❌ Too long (max {n} min here).",
        "too_big": "❌ File is {mb} MB — over Telegram's 50 MB limit.\nTry the audio version instead 👇",
        "failed": "❌ <b>Failed.</b>\n{hint}",
        "disabled": "🚫 This format is disabled in this group.",
        "hint_cookies": "YouTube blocked the server. The owner has been notified.",
        "hint_ffmpeg": "ffmpeg problem on the server. The owner has been notified.",
        "hint_unavail": "This video is unavailable.",
        "hint_retry": "Please try again in a moment.",
        "lang_pick": "🌐 <b>Choose your language</b>",
        "lang_set": "✅ Language set to <b>{name}</b>",
        "lyr_usage": "🎤 Send the song name.\n<b>Example:</b> <code>/lyrics Tum Hi Ho</code>",
        "lyr_search": "🎤 <b>Looking for lyrics…</b>\n<i>{q}</i>",
        "lyr_none": "😕 <b>Lyrics not found.</b>\nTry <code>/lyrics artist song name</code>.",
        "lyr_fail": "❌ Lyrics service is not responding. Try again later.",
        "st_title": "📊 <b>Bot statistics</b>\n",
        "st_users": "Users",
        "st_total": "Total downloads",
        "st_today": "Today",
        "st_audio": "Audio",
        "st_video": "Video",
        "st_you": "Your downloads",
        "st_top": "🏆 <b>Top songs</b>",
        "st_none": "No data yet",
        "inl_open": "🎧 Open bot",
        "unk_suggest": "❌ <code>/{cmd}</code> is not a command.\n✅ Did you mean <b>/{sug}</b>?\n\n<b>Example:</b> <code>{ex}</code>",
        "unk_list": "❌ <code>/{cmd}</code> is not a command.\n\n📋 <b>Available commands</b>\n{lst}",
    },
    "ur": {
        "rec_usage": "🎧 <b>گانا پہچانیں</b>\n\nمجھے <b>وائس نوٹ</b>، آڈیو یا ویڈیو کلپ بھیجیں — یا اس پر /find سے جواب دیں — میں گانا بتا دوں گا۔",
        "rec_listening": "🎧 <b>سن رہا ہوں…</b>\nگانا پہچانا جا رہا ہے، انتظار کریں۔",
        "rec_found": "✅ <b>گانا مل گیا!</b>\n\n🎶 <b>{title}</b>\n👤 {artist}{album}\n\n👇 نیچے سے ڈاؤنلوڈ کریں:",
        "rec_none": "😕 <b>میں یہ گانا پہچان نہیں سکا۔</b>\nزیادہ صاف کلپ (10–20 سیکنڈ، آواز بلند) بھیجیں۔",
        "rec_fail": "❌ پہچان کی سروس ابھی کام نہیں کر رہی۔ بعد میں کوشش کریں۔",
        "rec_limit": "⏳ روزانہ کی حد پوری ہو گئی (دن میں <b>{n}</b> بار)۔ کل دوبارہ کوشش کریں۔",
        "rec_big": "❌ فائل بہت بڑی ہے۔ 20 MB سے چھوٹا کلپ بھیجیں۔",
        "rec_help": "🎧 /find — وائس/آڈیو/ویڈیو پر جواب دے کر گانا پہچانیں (یا پرائیویٹ چیٹ میں بھیج دیں)",
        "join_text": "🔒 <b>جوائن کرنا ضروری ہے</b>\n\nبوٹ استعمال کرنے کے لیے نیچے دیے گئے چینل/گروپ جوائن کریں،\nپھر <b>✅ میں نے جوائن کر لیا</b> دبائیں۔",
        "join_btn": "جوائن کریں: {title}",
        "join_done": "✅ میں نے جوائن کر لیا",
        "join_not_yet": "❌ آپ نے ابھی سب جوائن نہیں کیے!",
        "join_first": "🔒 پہلے جوائن کریں",
        "join_ok": "✅ <b>تصدیق ہو گئی!</b>\n\nگانے کا نام بھیجیں یا /song استعمال کریں 🎧",
        "join_verified": "✅ تصدیق ہو گئی!",
        "banned": "🚫 آپ کو اس بوٹ کے استعمال سے بلاک کر دیا گیا ہے۔",
        "maintenance": "🛠 <b>مینٹیننس موڈ</b>\n\nبوٹ پر ابھی کام جاری ہے۔ تھوڑی دیر بعد کوشش کریں۔",
        "start": (
            "🎧 <b>میوزک اور ویڈیو ڈاؤنلوڈر</b>\n\nہیلو <b>{name}</b>! 👋\n"
            "مجھے <b>گانے کا نام</b> یا <b>یوٹیوب لنک</b> بھیجیں، میں آپ کو یہ دوں گا:\n\n"
            "🎵 <b>آڈیو</b> — اعلیٰ کوالٹی\n🎬 <b>ویڈیو</b> — 480p\n\n"
            "⚡ <b>فوری کمانڈز</b>\n<code>/song Tum Hi Ho a</code> → 🎵 آڈیو\n"
            "<code>/song Tum Hi Ho v</code> → 🎬 ویڈیو (480p)\n\n"
            "✨ <i>یا صرف نام لکھیں اور فہرست میں سے چنیں۔</i>"
        ),
        "help": (
            "📖 <b>استعمال کا طریقہ</b>\n\n"
            "🎵 <code>/song Tum Hi Ho a</code> — <b>آڈیو</b> حاصل کریں\n"
            "🎬 <code>/song Tum Hi Ho v</code> — <b>ویڈیو</b> حاصل کریں (ہمیشہ 480p)\n"
            "<b>A</b> = آڈیو · <b>V</b> = ویڈیو\n\n"
            "🔎 <code>/search Tum Hi Ho</code> — فہرست سے چنیں\n"
            "🎤 <code>/lyrics Tum Hi Ho</code> — گانے کے بول\n"
            "📊 /stats — بوٹ کے اعداد و شمار\n🌐 /lang — زبان تبدیل کریں\n"
            "🔍 ان لائن: کسی بھی چیٹ میں <code>@{bot} گانے کا نام</code> لکھیں\n\n"
            "💡 <b>a</b>/<b>v</b> کے بغیر میں فہرست دکھاؤں گا۔\n"
            "🔗 آپ یوٹیوب لنک بھی بھیج سکتے ہیں۔\n📦 زیادہ سے زیادہ سائز: 50 MB۔"
        ),
        "search_usage": "🔎 گانے کا نام بھی لکھیں۔\n<code>/search On Top Karan Aujla</code>",
        "song_usage": "🎵 گانے کا نام بھی لکھیں۔\n<b>آڈیو:</b> <code>/song DXB Karan Aujla a</code>\n<b>ویڈیو:</b> <code>/song DXB Karan Aujla v</code>",
        "fetching": "⏳ <b>معلومات حاصل کی جا رہی ہیں…</b>",
        "bad_link": "❌ یہ لنک پڑھا نہیں جا سکا۔ بعد میں کوشش کریں۔",
        "load_failed": "❌ یہ ویڈیو لوڈ نہیں ہو سکی۔ دوبارہ تلاش کریں۔",
        "searching": "🔎 <b>تلاش جاری ہے…</b>\n<i>{q}</i>",
        "search_failed": "❌ <b>تلاش ناکام ہو گئی۔</b>\n{hint}",
        "no_results": "😕 <b>کوئی نتیجہ نہیں ملا۔</b>\nفنکار کا نام بھی لکھ کر دیکھیں۔",
        "results_title": "🔎 <b>نتائج:</b> <i>{q}</i>\n",
        "tap": "\n👇 <i>چننے کے لیے بٹن یا نمبر دبائیں</i>",
        "choose": "👇 <b>فارمیٹ منتخب کریں</b>",
        "views": "ویوز",
        "btn_audio": "🎵 آڈیو",
        "btn_video": "🎬 ویڈیو 480p",
        "btn_lyrics": "🎤 بول",
        "label_audio": "🎵 آڈیو",
        "label_video": "🎬 ویڈیو 480p",
        "downloading": "⏬ <b>ڈاؤنلوڈ ہو رہا ہے…</b>\n{label}\n<i>{title}</i>",
        "uploading": "⬆️ <b>اپلوڈ ہو رہا ہے…</b>\n{label}",
        "queue": "⏳ <b>آپ قطار میں #{n} پر ہیں</b>\n<i>{title}</i>\nسرور مصروف ہے — باری آتے ہی شروع کر دوں گا۔",
        "too_long": "❌ بہت لمبا ہے (یہاں زیادہ سے زیادہ {n} منٹ)۔",
        "too_big": "❌ فائل {mb} MB ہے — ٹیلیگرام کی 50 MB حد سے زیادہ۔\nآڈیو آزمائیں 👇",
        "failed": "❌ <b>ناکام۔</b>\n{hint}",
        "disabled": "🚫 اس گروپ میں یہ فارمیٹ بند ہے۔",
        "hint_cookies": "یوٹیوب نے سرور کو بلاک کر دیا۔ مالک کو اطلاع دے دی گئی ہے۔",
        "hint_ffmpeg": "سرور پر ffmpeg کا مسئلہ ہے۔ مالک کو اطلاع دے دی گئی ہے۔",
        "hint_unavail": "یہ ویڈیو دستیاب نہیں ہے۔",
        "hint_retry": "براہِ کرم تھوڑی دیر بعد دوبارہ کوشش کریں۔",
        "lang_pick": "🌐 <b>اپنی زبان منتخب کریں</b>",
        "lang_set": "✅ زبان <b>{name}</b> سیٹ ہو گئی",
        "lyr_usage": "🎤 گانے کا نام لکھیں۔\n<b>مثال:</b> <code>/lyrics Tum Hi Ho</code>",
        "lyr_search": "🎤 <b>بول تلاش کیے جا رہے ہیں…</b>\n<i>{q}</i>",
        "lyr_none": "😕 <b>بول نہیں ملے۔</b>\n<code>/lyrics فنکار گانے کا نام</code> آزمائیں۔",
        "lyr_fail": "❌ بول والی سروس جواب نہیں دے رہی۔ بعد میں کوشش کریں۔",
        "st_title": "📊 <b>بوٹ کے اعداد و شمار</b>\n",
        "st_users": "صارفین",
        "st_total": "کل ڈاؤنلوڈ",
        "st_today": "آج",
        "st_audio": "آڈیو",
        "st_video": "ویڈیو",
        "st_you": "آپ کے ڈاؤنلوڈ",
        "st_top": "🏆 <b>مقبول گانے</b>",
        "st_none": "ابھی کوئی ڈیٹا نہیں",
        "inl_open": "🎧 بوٹ کھولیں",
        "unk_suggest": "❌ <code>/{cmd}</code> کوئی کمانڈ نہیں ہے۔\n✅ کیا آپ کا مطلب <b>/{sug}</b> تھا؟\n\n<b>مثال:</b> <code>{ex}</code>",
        "unk_list": "❌ <code>/{cmd}</code> کوئی کمانڈ نہیں ہے۔\n\n📋 <b>دستیاب کمانڈز</b>\n{lst}",
    },
    "hi": {
        "rec_usage": "🎧 <b>गाना पहचानें</b>\n\nमुझे <b>वॉइस नोट</b>, ऑडियो या वीडियो क्लिप भेजें — या उस पर /find से रिप्लाई करें — मैं गाना बता दूँगा।",
        "rec_listening": "🎧 <b>सुन रहा हूँ…</b>\nगाना पहचाना जा रहा है, कृपया रुकें।",
        "rec_found": "✅ <b>गाना मिल गया!</b>\n\n🎶 <b>{title}</b>\n👤 {artist}{album}\n\n👇 नीचे से डाउनलोड करें:",
        "rec_none": "😕 <b>मैं यह गाना पहचान नहीं सका।</b>\nज़्यादा साफ़ क्लिप (10–20 सेकंड, तेज़ आवाज़) भेजें।",
        "rec_fail": "❌ पहचान सेवा अभी काम नहीं कर रही। बाद में कोशिश करें।",
        "rec_limit": "⏳ रोज़ की सीमा पूरी हो गई (दिन में <b>{n}</b> बार)। कल फिर कोशिश करें।",
        "rec_big": "❌ फ़ाइल बहुत बड़ी है। 20 MB से छोटी क्लिप भेजें।",
        "rec_help": "🎧 /find — वॉइस/ऑडियो/वीडियो पर रिप्लाई करके गाना पहचानें (या प्राइवेट चैट में भेजें)",
        "join_text": "🔒 <b>जॉइन करना ज़रूरी है</b>\n\nबॉट इस्तेमाल करने के लिए नीचे दिए चैनल/ग्रुप जॉइन करें,\nफिर <b>✅ मैंने जॉइन कर लिया</b> दबाएँ।",
        "join_btn": "जॉइन करें: {title}",
        "join_done": "✅ मैंने जॉइन कर लिया",
        "join_not_yet": "❌ आपने अभी सब जॉइन नहीं किए!",
        "join_first": "🔒 पहले जॉइन करें",
        "join_ok": "✅ <b>पुष्टि हो गई!</b>\n\nगाने का नाम भेजें या /song इस्तेमाल करें 🎧",
        "join_verified": "✅ पुष्टि हो गई!",
        "banned": "🚫 आपको इस बॉट के इस्तेमाल से बैन कर दिया गया है।",
        "maintenance": "🛠 <b>मेंटेनेंस मोड</b>\n\nबॉट पर अभी काम चल रहा है। कृपया थोड़ी देर बाद कोशिश करें।",
        "start": (
            "🎧 <b>म्यूज़िक और वीडियो डाउनलोडर</b>\n\nनमस्ते <b>{name}</b>! 👋\n"
            "मुझे <b>गाने का नाम</b> या <b>YouTube लिंक</b> भेजें, मैं आपको दूँगा:\n\n"
            "🎵 <b>ऑडियो</b> — हाई क्वालिटी\n🎬 <b>वीडियो</b> — 480p\n\n"
            "⚡ <b>क्विक कमांड</b>\n<code>/song Tum Hi Ho a</code> → 🎵 ऑडियो\n"
            "<code>/song Tum Hi Ho v</code> → 🎬 वीडियो (480p)\n\n"
            "✨ <i>या बस नाम लिखें और लिस्ट से चुनें।</i>"
        ),
        "help": (
            "📖 <b>कैसे इस्तेमाल करें</b>\n\n"
            "🎵 <code>/song Tum Hi Ho a</code> — <b>ऑडियो</b> पाएँ\n"
            "🎬 <code>/song Tum Hi Ho v</code> — <b>वीडियो</b> पाएँ (हमेशा 480p)\n"
            "<b>A</b> = ऑडियो · <b>V</b> = वीडियो\n\n"
            "🔎 <code>/search Tum Hi Ho</code> — सूची से चुनें\n"
            "🎤 <code>/lyrics Tum Hi Ho</code> — गाने के बोल\n"
            "📊 /stats — बॉट के आँकड़े\n🌐 /lang — भाषा बदलें\n"
            "🔍 इनलाइन: किसी भी चैट में <code>@{bot} गाने का नाम</code> लिखें\n\n"
            "💡 <b>a</b>/<b>v</b> के बिना मैं लिस्ट दिखाऊँगा।\n"
            "🔗 आप YouTube लिंक भी भेज सकते हैं।\n📦 अधिकतम साइज़: 50 MB।"
        ),
        "search_usage": "🔎 गाने का नाम भी लिखें।\n<code>/search On Top Karan Aujla</code>",
        "song_usage": "🎵 गाने का नाम भी लिखें।\n<b>ऑडियो:</b> <code>/song DXB Karan Aujla a</code>\n<b>वीडियो:</b> <code>/song DXB Karan Aujla v</code>",
        "fetching": "⏳ <b>जानकारी ली जा रही है…</b>",
        "bad_link": "❌ यह लिंक पढ़ा नहीं जा सका। बाद में कोशिश करें।",
        "load_failed": "❌ यह वीडियो लोड नहीं हो सका। फिर से खोजें।",
        "searching": "🔎 <b>खोज जारी है…</b>\n<i>{q}</i>",
        "search_failed": "❌ <b>खोज विफल रही।</b>\n{hint}",
        "no_results": "😕 <b>कोई नतीजा नहीं मिला।</b>\nकलाकार का नाम भी जोड़कर देखें।",
        "results_title": "🔎 <b>नतीजे:</b> <i>{q}</i>\n",
        "tap": "\n👇 <i>चुनने के लिए बटन या नंबर दबाएँ</i>",
        "choose": "👇 <b>फ़ॉर्मैट चुनें</b>",
        "views": "व्यूज़",
        "btn_audio": "🎵 ऑडियो",
        "btn_video": "🎬 वीडियो 480p",
        "btn_lyrics": "🎤 बोल",
        "label_audio": "🎵 ऑडियो",
        "label_video": "🎬 वीडियो 480p",
        "downloading": "⏬ <b>डाउनलोड हो रहा है…</b>\n{label}\n<i>{title}</i>",
        "uploading": "⬆️ <b>अपलोड हो रहा है…</b>\n{label}",
        "queue": "⏳ <b>आप लाइन में #{n} पर हैं</b>\n<i>{title}</i>\nसर्वर व्यस्त है — आपकी बारी आते ही शुरू कर दूँगा।",
        "too_long": "❌ बहुत लंबा है (यहाँ अधिकतम {n} मिनट)।",
        "too_big": "❌ फ़ाइल {mb} MB है — टेलीग्राम की 50 MB सीमा से ज़्यादा।\nऑडियो आज़माएँ 👇",
        "failed": "❌ <b>विफल।</b>\n{hint}",
        "disabled": "🚫 इस ग्रुप में यह फ़ॉर्मैट बंद है।",
        "hint_cookies": "YouTube ने सर्वर को ब्लॉक कर दिया। मालिक को सूचित कर दिया गया है।",
        "hint_ffmpeg": "सर्वर पर ffmpeg की समस्या है। मालिक को सूचित कर दिया गया है।",
        "hint_unavail": "यह वीडियो उपलब्ध नहीं है।",
        "hint_retry": "कृपया थोड़ी देर बाद फिर कोशिश करें।",
        "lang_pick": "🌐 <b>अपनी भाषा चुनें</b>",
        "lang_set": "✅ भाषा <b>{name}</b> सेट हो गई",
        "lyr_usage": "🎤 गाने का नाम लिखें।\n<b>उदाहरण:</b> <code>/lyrics Tum Hi Ho</code>",
        "lyr_search": "🎤 <b>बोल खोजे जा रहे हैं…</b>\n<i>{q}</i>",
        "lyr_none": "😕 <b>बोल नहीं मिले।</b>\n<code>/lyrics कलाकार गाने का नाम</code> आज़माएँ।",
        "lyr_fail": "❌ बोल वाली सेवा जवाब नहीं दे रही। बाद में कोशिश करें।",
        "st_title": "📊 <b>बॉट के आँकड़े</b>\n",
        "st_users": "यूज़र",
        "st_total": "कुल डाउनलोड",
        "st_today": "आज",
        "st_audio": "ऑडियो",
        "st_video": "वीडियो",
        "st_you": "आपके डाउनलोड",
        "st_top": "🏆 <b>टॉप गाने</b>",
        "st_none": "अभी कोई डेटा नहीं",
        "inl_open": "🎧 बॉट खोलें",
        "unk_suggest": "❌ <code>/{cmd}</code> कोई कमांड नहीं है।\n✅ क्या आपका मतलब <b>/{sug}</b> था?\n\n<b>उदाहरण:</b> <code>{ex}</code>",
        "unk_list": "❌ <code>/{cmd}</code> कोई कमांड नहीं है।\n\n📋 <b>उपलब्ध कमांड</b>\n{lst}",
    },
}


def L(uid: int) -> str:
    """Return user's language code ('en', 'ur', or 'hi')."""
    return str(db["ulang"].get(str(uid), "en"))


def tr(lang: str, key: str, **kw: object) -> str:
    """Translate string key into `lang` with fallback to English."""
    s = STR.get(lang, {}).get(key) or STR["en"][key]
    return s.format(**kw) if kw else s


def help_text(lang: str, bot_username: str | None) -> str:
    """Build full /help text in the user's language."""
    return (
        tr(lang, "help", bot=str(bot_username or "bot"))
        + "\n"
        + tr(lang, "rec_help")
        + "\n"
        + NEW_HELP
    )
