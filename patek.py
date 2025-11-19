#!/usr/bin/env python3
"""
Script untuk santri — otomatis unduh, ekstrak, dan perbaiki Chromium portable.

FITUR:
- Mode Setup (khusus admin, dijalankan sekali untuk konfigurasi awal).
- Mode Admin (untuk mengubah password user dan upload ke GitHub).
- Mode User (untuk mengunduh Chromium setelah setup).
- Mengunci wget dan menggunakan aturan sudo untuk eksekusi yang aman.
"""

import os
import shutil
import subprocess
import zipfile
import getpass
import sys
import stat
import time
import http.server
import socketserver
import json

# --- WARNA ---
class C:
    G = '\033[92m' # GREEN
    Y = '\033[93m' # YELLOW
    R = '\033[91m' # RED
    B = '\033[94m' # BLUE
    C = '\033[96m' # CYAN
    END = '\033[0m' # RESET

# --- KONFIGURASI ---
ADMIN_PASSWORD = "s4ntr1"
USER_PASSWORD  = "patek lah"
URL = "https://download-chromium.appspot.com/dl/Linux_x64?type=snapshots"
FILE_NAME = "chrome-linux.zip"
WORK_DIR = "chrome-linux"
SUDOERS_FILE = "/etc/sudoers.d/99-modifan-rule"

# --- KONFIGURASI TAMBAHAN UNTUK SANTRI ---
# Alamat IP server untuk homepage dan halaman blokir
SANTRI_SERVER = "http://192.168.1.5:8082"

# --- FUNGSI HELPERS ---
def slow_print(text, speed=0.02):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)
    print()

def try_chmod_exec(path):
    try:
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return True
    except Exception: return False

# --- FUNGSI SETUP (KHUSUS ADMIN) ---
def initial_setup(username, script_path):
    slow_print(f"{C.Y}[*] Memulai proses setup awal untuk keamanan skrip...{C.END}")
    if os.geteuid() != 0:
        print(f"{C.R}[!] Error: Mode setup harus dijalankan sebagai root. Gunakan: sudo python3 {script_path} --setup <nama_user>{C.END}")
        sys.exit(1)
    wget_path = shutil.which("wget")
    if not wget_path:
        print(f"{C.R}[!] Error: 'wget' tidak ditemukan. Mohon install wget terlebih dahulu.{C.END}")
        sys.exit(1)
    print(f"{C.Y}[*] Mengunci {wget_path} agar hanya bisa diakses root...{C.END}")
    try:
        subprocess.run(['chown', 'root:root', wget_path], check=True)
        subprocess.run(['chmod', '700', wget_path], check=True)
        print(f"  {C.G}[✓] Izin {wget_path} diubah menjadi 700.{C.END}")
    except Exception as e:
        print(f"{C.R}[!] Gagal mengunci wget: {e}{C.END}")
        sys.exit(1)
    rule = f"{username} ALL=(root) NOPASSWD: /usr/bin/python3 {script_path}"
    print(f'''
{C.Y}[*] Membuat aturan sudo di {SUDOERS_FILE}...
    Aturan: {rule}{C.END}''')
    try:
        with open(SUDOERS_FILE, 'w') as f:
            f.write(rule + '\n')
        os.chmod(SUDOERS_FILE, 0o440)
        print(f"  {C.G}[✓] Aturan sudo berhasil dibuat.{C.END}")
    except Exception as e:
        print(f"{C.R}[!] Gagal membuat file sudoers: {e}{C.END}")
        sys.exit(1)
    slow_print(f"\n{C.G}[✓] Setup Selesai! Pengguna '{username}' sekarang bisa menjalankan skrip dengan: sudo python3 {script_path}{C.END}")

# --- FUNGSI ADMIN ---
def change_passwords():
    print(f"{C.Y}[*] Mengubah Password...{C.END}")
    script_path = os.path.abspath(__file__)
    try:
        with open(script_path, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"{C.R}[!] Gagal membaca file skrip: {e}{C.END}")
        return
    new_lines = []
    pass_changed = False
    choice = input("Password mana yang ingin diubah? (1) Admin, (2) User, (3) Keduanya, (lainnya) Batal: ")
    new_admin_pass = None
    if choice in ['1', '3']:
        new_admin_pass = getpass.getpass("Masukkan password ADMIN baru: ")
    new_user_pass = None
    if choice in ['2', '3']:
        new_user_pass = getpass.getpass("Masukkan password USER baru: ")
    if not new_admin_pass and not new_user_pass:
        print(f"{C.Y}[i] Aksi dibatalkan.{C.END}")
        return
    for line in lines:
        if new_admin_pass and line.strip().startswith('ADMIN_PASSWORD'):
            new_lines.append(f'ADMIN_PASSWORD = "{new_admin_pass}"\n')
            pass_changed = True
        elif new_user_pass and line.strip().startswith('USER_PASSWORD'):
            new_lines.append(f'USER_PASSWORD  = "{new_user_pass}"\n')
            pass_changed = True
        else:
            new_lines.append(line)
    if pass_changed:
        try:
            with open(script_path, 'w') as f:
                f.writelines(new_lines)
            print(f"{C.G}[✓] Password berhasil diubah.{C.END}")
            print(f"{C.Y}[!] Perubahan akan aktif setelah skrip dijalankan ulang.{C.END}")
        except Exception as e:
            print(f"{C.R}[!] Gagal menulis perubahan ke file: {e}{C.END}")
    else:
        print(f"{C.Y}[i] Tidak ada password yang diubah.{C.END}")

def admin_actions():
    slow_print(f"{C.G}[*] Mode ADMIN aktif.{C.END}")
    while True:
        print(f"\n{C.B}--- Menu Admin ---{C.END}")
        print("1. Ubah Password")
        print(f"2. {C.Y}Keluar{C.END}")
        choice = input("Masukkan pilihan: ")
        if choice == '1':
            change_passwords()
        elif choice == '2':
            print(f"{C.Y}[i] Keluar dari mode admin.{C.END}")
            break
        else:
            print(f"{C.R}[!] Pilihan tidak valid.{C.END}")

# --- FUNGSI UTAMA ---
def secure_permissions(chromium_dir, extension_dir, user):
    print(f"{C.Y}[*] Menerapkan izin keamanan berlapis...{C.END}")
    try:
        # 1. Seluruh direktori instalasi dimiliki oleh user terlebih dahulu agar chrome bisa menulis cache
        print(f"  {C.Y}[i] Mengatur kepemilikan awal ke {user}...{C.END}")
        subprocess.run(['chown', '-R', f'{user}:{user}', chromium_dir], check=True)
        print(f"  {C.G}[✓] Kepemilikan awal diatur ke {user}.{C.END}")

        # 2. Kunci folder ekstensi, hanya bisa dibaca oleh user
        print(f"  {C.Y}[i] Mengunci folder ekstensi...{C.END}")
        subprocess.run(['chown', '-R', 'root:root', extension_dir], check=True)
        subprocess.run(['chmod', '755', extension_dir], check=True) # rwxr-xr-x for dir
        for root, dirs, files in os.walk(extension_dir):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
            for f in files:
                os.chmod(os.path.join(root, f), 0o644) # rw-r--r-- for files
        print(f"  {C.G}[✓] Folder ekstensi dikunci (read-only untuk user).{C.END}")

        # 3. Kunci skrip pembungkus dan executable asli
        print(f"  {C.Y}[i] Mengunci file executable chrome...{C.END}")
        chrome_wrapper_path = os.path.join(chromium_dir, "chrome")
        chrome_real_path = os.path.join(chromium_dir, ".chrome")
        if os.path.exists(chrome_wrapper_path):
            os.chown(chrome_wrapper_path, 0, 0)
            os.chmod(chrome_wrapper_path, 0o755) # rwxr-xr-x
        if os.path.exists(chrome_real_path):
            os.chown(chrome_real_path, 0, 0)
            os.chmod(chrome_real_path, 0o755) # rwxr-xr-x
        print(f"  {C.G}[✓] File executable chrome dikunci.{C.END}")
        
    except Exception as e:
        print(f"{C.R}[!] Gagal menerapkan izin keamanan: {e}{C.END}")
        sys.exit(1)

def fix_chrome_permissions():
    print(f"{C.Y}[*] Memperbaiki izin file chrome agar executable...{C.END}")
    target_dir = "/home/santri/chrom/chrome-linux/chrome-linux"
    try:
        for root, _, files in os.walk(target_dir):
            for f in files:
                if f.startswith("chrome"):
                    path = os.path.join(root, f)
                    try_chmod_exec(path)
        print(f"  {C.G}[✓] Izin eksekusi file chrome telah diatur.{C.END}")
    except Exception as e:
        print(f"{C.R}[!] Gagal mengubah izin eksekusi: {e}{C.END}")

def create_wrapper_script(chromium_dir, extension_path):
    print(f"{C.Y}[*] Membuat skrip pembungkus untuk chrome...{C.END}")
    chrome_real_path = os.path.join(chromium_dir, ".chrome")
    chrome_wrapper_path = os.path.join(chromium_dir, "chrome")
    
    try:
        # Ubah nama executable chrome yang asli jika belum ada
        if os.path.exists(chrome_wrapper_path) and not os.path.lexists(chrome_real_path):
            os.rename(chrome_wrapper_path, chrome_real_path)
            print(f"  {C.G}[✓] File chrome asli diubah namanya menjadi .chrome.{C.END}")

        # Buat skrip pembungkus
        wrapper_content = f'''#!/bin/bash
# Skrip Pembungkus untuk Chromium
# Memaksa pemuatan ekstensi keamanan dan menjalankan chrome asli.
SCRIPT_DIR=$(cd \"$(dirname \"$0\")\" && pwd)
exec \"$SCRIPT_DIR/.chrome\" --load-extension=\"{extension_path}\" \"$@\"
'''
        with open(chrome_wrapper_path, 'w') as f:
            f.write(wrapper_content)
        
        # Jadikan skrip pembungkus executable
        os.chmod(chrome_wrapper_path, 0o755)
        print(f"  {C.G}[✓] Skrip pembungkus chrome berhasil dibuat dan dijadikan executable.{C.END}")

    except Exception as e:
        print(f"{C.R}[!] Gagal membuat skrip pembungkus: {e}{C.END}")
        sys.exit(1)

def download_chromium():
    if os.path.exists(FILE_NAME): return
    print(f"{C.Y}[+] Mengunduh Chromium dari internet...{C.END}")
    try:
        subprocess.run(["wget", "-O", FILE_NAME, URL], check=True)
        print(f"{C.G}[✓] Unduhan selesai.{C.END}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"\n{C.R}[!] Gagal mengunduh Chromium.{C.END}")
        print(f"{C.R}[i] Detail Error: {e}{C.END}")
        sys.exit(1)

def extract_zip():
    print(f"{C.Y}[+] Mengekstrak file...{C.END}")
    with zipfile.ZipFile(FILE_NAME, 'r') as zf:
        zf.extractall(WORK_DIR)
    print(f"{C.G}[✓] Ekstraksi selesai.{C.END}")

def auth_mode():
    slow_print(f"{C.B}=== Autentikasi Santri ==={C.END}")
    pwd = getpass.getpass("Masukkan password: ")
    user = os.environ.get('SUDO_USER', 'unknown')
    if pwd == ADMIN_PASSWORD:
        return "admin"
    elif pwd == USER_PASSWORD:
        return "user"
    else:
        print(f"{C.R}[!] Password salah.{C.END}")
        sys.exit(1)

def apply_chromium_modifications(chromium_dir):
    print(f"{C.Y}[*] Menerapkan modifikasi kustom untuk Chromium...{C.END}")
    extension_dir = os.path.join(chromium_dir, "blokir")
    os.makedirs(extension_dir, exist_ok=True)
    # 1. manifest.json
    manifest_content = '''{
  "manifest_version": 3,
  "name": "Santri URL Guard",
  "version": "1.0",
  "description": "Blokir semua situs kecuali yang diizinkan dan arahkan ke halaman blokir.",
  "permissions": ["declarativeNetRequest", "declarativeNetRequestWithHostAccess", "tabs"],
  "host_permissions": ["<all_urls>"],
  "background": {
    "service_worker": "background.js"
  },
  "chrome_url_overrides": {
    "newtab": "redirect.html"
  }
}'''
    with open(os.path.join(extension_dir, "manifest.json"), 'w') as f:
        f.write(manifest_content)
    # 2. background.js
    background_js_content = '''const allowlist = [
  "http://192.168.1.5:8082/",
  "http://192.168.1.4/paccak",
  "https://github.com/",
  "https://glosbe.com/",
  "https://shell.cloud.google.com/",
  "https://chatgpt.com/",
  "https://etc.usf.edu/lit2go/books",
  "https://americanliterature.com/",
  "https://duolingo.com/",
  "https://www.duolingo.com/",
  "https://accounts.google.com/",
  "https://myaccount.google.com/",
  "https://www.accounts.google.com/",
  "https://storyberries.com/",
  "https://www.storyberries.com/",
  "https://zenius.net/",
  "https://tryout.zenius.net/",
  "https://www.zenius.net/",
  "https://pahamify.com/",
  "https://www.pahamify.com/",
  "https://khanacademy.org/",
  "https://www.khanacademy.org/",
  "https://dictionary.cambridge.org/",
  "https://www.dictionary.cambridge.org/",
  "https://manggisan.com/",
  "https://fudc.manggisan.com/",
  "https://www.manggisan.com/",
  "https://altafsir.com/",
  "https://www.altafsir.com/",
  "https://piss-ktb.com/",
  "https://www.piss-ktb.com/",
  "https://shamela.ws/",
  "https://nu.or.id/",
  "https://quran.kemenag.go.id/",
  "https://dorar.net/"
];

async function setupRules() {
  const rules = [];
  rules.push({
    id: 1,
    priority: 1,
    action: {
      type: "redirect",
      redirect: { url: "http://192.168.1.5:8082/block?u=" }
    },
    condition: { urlFilter: "*", resourceTypes: ["main_frame"] }
  });
  allowlist.forEach((url, index) => {
    rules.push({
      id: index + 100,
      priority: 2,
      action: { type: "allow" },
      condition: { urlFilter: url, resourceTypes: ["main_frame"] }
    });
  });
  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: Array.from({ length: 1000 }, (_, i) => i + 1),
    addRules: rules
  });
}

chrome.runtime.onInstalled.addListener(setupRules);
chrome.runtime.onStartup.addListener(setupRules);

// Setiap kali tab baru dibuat (bukan startup)
chrome.tabs.onCreated.addListener((tab) => {
  // Jika URL belum ada (baru dibuat)
  if (!tab.pendingUrl && !tab.url) return;
  // Jika bukan halaman home (startup), arahkan ke block
  if (!tab.url.includes("192.168.1.5:8082/home")) {
    chrome.tabs.update(tab.id, { url: "http://192.168.1.5:8082/block?u=" });
  }
});'''
    with open(os.path.join(extension_dir, "background.js"), 'w') as f:
        f.write(background_js_content)
    # 3. redirect.html
    redirect_html_content = '''<!DOCTYPE html>
<html>
  <head>
    <meta http-equiv="refresh" content="0; url=http://192.168.1.5:8082/home" />
  </head>
  <body></body>
</html>'''
    with open(os.path.join(extension_dir, "redirect.html"), 'w') as f:
        f.write(redirect_html_content)
    print(f"  {C.G}[✓] Ekstensi kustom berhasil diterapkan.{C.END}")
    return extension_dir

def main():
    os.system('clear')
    if len(sys.argv) > 1 and sys.argv[1] == '--setup':
        if len(sys.argv) != 3: sys.exit(f"{C.R}Penggunaan: sudo python3 modifan.py --setup <nama_user>{C.END}")
        initial_setup(username=sys.argv[2], script_path=os.path.abspath(__file__))
        sys.exit(0)
    if os.geteuid() != 0:
        sys.exit(f"{C.R}[!] Error: Skrip ini harus dijalankan dengan 'sudo'.\n   Gunakan: sudo python3 {os.path.abspath(__file__)}{C.END}")
    mode = auth_mode()
    print(f"\n{C.Y}[i] Mode aktif: {mode.upper()}{C.END}\n")
    if mode == "admin":
        admin_actions()
    elif mode == "user":
        # Cek apakah instalasi sudah ada
        if os.path.exists(WORK_DIR) or os.path.exists(FILE_NAME):
            print(f"{C.Y}[i] Ditemukan instalasi Chromium yang sudah ada (folder atau file zip).{C.END}")
            print(f"{C.Y}[i] Hapus folder '{WORK_DIR}' dan file '{FILE_NAME}' jika ingin menginstal ulang.{C.END}")
            # Opsi untuk menjalankan chrome yang sudah ada
            chromium_dir = os.path.abspath(WORK_DIR)
            if os.path.exists(os.path.join(chromium_dir, 'chrome')):
                launch_command = f"cd {chromium_dir} && ./chrome"
                print(f"{C.Y}[i] Untuk menjalankan Chromium yang sudah ada, keluar dari mode sudo dan gunakan perintah:\n  {C.C}{launch_command}{C.END}")
            return
        if input(f"{C.Y}Anda akan mengunduh & menginstal Chromium. Lanjutkan? (y/N): {C.END}").lower() == 'y':
            try:
                user = os.environ.get('SUDO_USER', 'unknown')
                slow_print(f"\n{C.Y}[*] Memulai proses instalasi...{C.END}")
                download_chromium()
                extract_zip()
                # Hapus file zip setelah ekstraksi
                try:
                    print(f"{C.Y}[*] Menghapus file {FILE_NAME}...{C.END}")
                    os.remove(FILE_NAME)
                    print(f"  {C.G}[✓] File zip berhasil dihapus.{C.END}")
                except OSError as e:
                    print(f"{C.R}[!] Gagal menghapus file zip: {e}{C.END}")
                
                # Path instalasi dihardcode sesuai perintah user
                chromium_dir = "/home/santri/chrom/chrome-linux/chrome-linux"
                
                # Pastikan direktori target ada
                if not os.path.isdir(chromium_dir):
                    print(f"{C.R}[!] Direktori instalasi Chromium tidak ditemukan di lokasi yang diharapkan: {chromium_dir}{C.END}")
                    print(f"{C.R}[!] Pastikan file zip diekstrak dengan benar ke lokasi tersebut atau buat folder secara manual.{C.END}")
                    sys.exit(1)

                # Terapkan modifikasi dan dapatkan path ekstensi
                extension_dir = apply_chromium_modifications(chromium_dir)
                
                # Perbaiki izin file-file chrome
                fix_chrome_permissions()
                
                # Buat skrip pembungkus
                create_wrapper_script(chromium_dir, extension_dir)
                
                # Terapkan izin keamanan berlapis
                secure_permissions(chromium_dir, extension_dir, user)
                
                print(f"\n{C.G}[✓] Chromium berhasil diinstal dan dikunci dengan 2 lapisan keamanan!{C.END}")
                launch_command = f"cd {chromium_dir} && ./chrome"
                print(f"\n{C.Y}Instalasi selesai. Untuk menjalankan Chromium, keluar dari mode sudo dan gunakan perintah berikut di terminal biasa:\n  {C.C}{launch_command}{C.END}")
            except Exception as e:
                print(f"\n{C.R}[!] Terjadi kesalahan: {e}{C.END}")
        else:
            print(f"{C.Y}[i] Instalasi dibatalkan.{C.END}")

if __name__ == "__main__":
    main()
