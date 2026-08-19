oke untuk sistem nya kurang lebih sudah ok, 
dan karna saya mau jual ini, jadi harus user yang sudah saya daftarkan aja yang bisa akses.
1 user 1 API (bisa set ulang api sendiri (self service))
jadi nanti di tele nya bisa set API ada piihan setting

awal welcome message
Flow Pertama Kali User
Saat /start

Cek:

Sudah terdaftar dan aktif?
ya → dashboard
jika tidak aktif/subscription expired 
belum → deny (kontak admin)


dan list fitur apa aja yang bisa user akses (sekarang hanya motion control tapi kedepannya bakalan ada lagi, jadi di db bisa set user bisa akses fitur apa aja)
1. Motion Control
2. Account Setting

Account Setting
👤 Account
🔑 API Settings
💳 Subscription
📜 History

Subscription ada 14 hari, 30 hari, 90 hari, 180 hari, 360 hari (disetting di db)



