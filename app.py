import os
from typing import Any, Dict, List, Optional, Tuple

import mysql.connector
from mysql.connector import Error, IntegrityError
import pandas as pd
import streamlit as st


# ============================================================
# KONFIGURASI HALAMAN
# ============================================================

st.set_page_config(
    page_title="Sistem Penjadwalan Ruang Kelas",
    page_icon="📅",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container { padding-top: 1.4rem; }
        div[data-testid="stMetricValue"] { font-size: 1.8rem; }
        .small-text { color:#4b5563; font-size:0.9rem; }
        .badge {
            display:inline-block;
            padding:4px 8px;
            border-radius:6px;
            background:#e5e7eb;
            font-size:12px;
            font-weight:600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# KONFIGURASI DATABASE MYSQL
# Untuk deploy Streamlit Cloud, isi di App Settings > Secrets:
#
[mysql]
host = "sql.freedb.tech"
user = "u_z6M1TI"
password = "9PerXwHpsuQf"
database = "freedb_GGSui8CO"
# ============================================================


def get_db_config():
    try:
        return {
            "host": st.secrets["mysql"]["host"],
            "port": int(st.secrets["mysql"].get("port", 3306)),
            "user": st.secrets["mysql"]["user"],
            "password": st.secrets["mysql"]["password"],
            "database": st.secrets["mysql"]["database"],
        }
    except Exception:
        return {
            "host": os.getenv("DB_HOST", ""),
            "port": int(os.getenv("DB_PORT", 3306)),
            "user": os.getenv("DB_USER", ""),
            "password": os.getenv("DB_PASSWORD", ""),
            "database": os.getenv("DB_NAME", ""),
        }


class Database:
    """Wrapper database agar query lama tetap bisa memakai tanda tanya sebagai placeholder."""

    def __init__(self):
        config = get_db_config()
        if not all([config["host"], config["user"], config["database"]]):
            st.error("Konfigurasi database belum lengkap. Isi Secrets Streamlit terlebih dahulu.")
            st.stop()
        try:
            self.conn = mysql.connector.connect(**config)
        except mysql.connector.Error as err:
            st.error("Gagal terhubung ke database MySQL.")
            st.write("Kode error:", err.errno)
            st.write("Pesan error:", err.msg)
            st.stop()

    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None):
        sql = sql.replace("INSERT OR IGNORE", "INSERT IGNORE")
        sql = sql.replace("?", "%s")
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(sql, params or ())
        return cursor

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()


def get_db() -> Database:
    return Database()


def fetch_all(sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
    db = get_db()
    try:
        return db.execute(sql, params).fetchall()
    finally:
        db.close()


def fetch_one(sql: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[Dict[str, Any]]:
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


def run_write(callback, success_message: str, integrity_message: str = "Data tidak dapat diproses.") -> None:
    db = get_db()
    try:
        callback(db)
        db.commit()
        st.success(success_message)
    except IntegrityError:
        db.rollback()
        st.error(integrity_message)
    except Error as exc:
        db.rollback()
        st.error(f"Terjadi error database: {exc}")
    finally:
        db.close()


def show_table(rows: List[Dict[str, Any]], empty_message: str = "Belum ada data.") -> None:
    if not rows:
        st.info(empty_message)
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def rerun_app() -> None:
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()


# ============================================================
# SESSION DAN AUTH
# ============================================================


def init_session() -> None:
    defaults = {
        "user_id": None,
        "username": None,
        "role": None,
        "ref_id": None,
        "page": None,
        "rekomendasi_jadwal_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def is_logged_in() -> bool:
    return st.session_state.get("user_id") is not None


def logout() -> None:
    for key in ["user_id", "username", "role", "ref_id", "page", "rekomendasi_jadwal_id"]:
        st.session_state[key] = None
    rerun_app()


def login_page() -> None:
    st.title("Login Sistem Penjadwalan Ruang Kelas")
    st.caption("Masukkan username dan password sesuai akun yang sudah tersedia di database.")

    with st.form("form_login", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login", use_container_width=True)

    if submit:
        if not username or not password:
            st.warning("Username dan password wajib diisi.")
            return

        db = get_db()
        try:
            user = db.execute(
                "SELECT * FROM users WHERE username = ? AND password = ?",
                (username, password),
            ).fetchone()
        finally:
            db.close()

        if not user:
            st.error("Username atau password salah.")
            return

        st.session_state.user_id = user["id"]
        st.session_state.username = user["username"]
        st.session_state.role = user["role"]
        st.session_state.ref_id = user["ref_id"]
        st.success("Login berhasil.")
        rerun_app()


def sidebar_menu() -> None:
    role = st.session_state.role
    st.sidebar.title("Menu")
    st.sidebar.write(f"Login sebagai **{st.session_state.username}**")
    st.sidebar.caption(f"Role: {role}")

    if role == "admin":
        pages = ["Dashboard Admin", "Kelola Data", "Persetujuan Jadwal"]
    elif role == "dosen":
        pages = ["Dashboard Dosen", "Pilih Jadwal", "Rekomendasi"]
    elif role == "mahasiswa":
        pages = ["Dashboard Mahasiswa"]
    else:
        pages = []

    if st.session_state.page not in pages:
        st.session_state.page = pages[0] if pages else None

    selected = st.sidebar.radio(
        "Pilih halaman",
        pages,
        index=pages.index(st.session_state.page) if st.session_state.page in pages else 0,
    )
    st.session_state.page = selected

    st.sidebar.divider()
    if st.sidebar.button("Logout", use_container_width=True):
        logout()


# ============================================================
# ALGORITMA REKOMENDASI / BRANCH AND BOUND INTERAKTIF
# ============================================================


def waktu_ke_menit(jam: Any) -> int:
    bagian = str(jam).split(":")
    return int(bagian[0]) * 60 + int(bagian[1])


def waktu_overlap(slot_a: Dict[str, Any], slot_b: Dict[str, Any]) -> bool:
    if slot_a["hari"] != slot_b["hari"]:
        return False
    mulai_a = waktu_ke_menit(slot_a["jam_mulai"])
    selesai_a = waktu_ke_menit(slot_a["jam_selesai"])
    mulai_b = waktu_ke_menit(slot_b["jam_mulai"])
    selesai_b = waktu_ke_menit(slot_b["jam_selesai"])
    return mulai_a < selesai_b and mulai_b < selesai_a


def get_jadwal_aktif(db: Database, exclude_jadwal_id: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            j.id,
            j.kode_matkul,
            j.nip,
            j.kode_ruang,
            j.kode_slot,
            j.status_jadwal,
            m.nama_matkul,
            m.kelas,
            r.nama_ruang,
            r.jenis_ruang,
            s.hari,
            s.jam_mulai,
            s.jam_selesai
        FROM jadwal j
        JOIN mata_kuliah m ON j.kode_matkul = m.kode_matkul
        LEFT JOIN ruang r ON j.kode_ruang = r.kode_ruang
        LEFT JOIN slot_waktu s ON j.kode_slot = s.kode_slot
        WHERE j.status_jadwal IN ('menunggu_persetujuan', 'final')
    """
    params: List[Any] = []
    if exclude_jadwal_id is not None:
        sql += " AND j.id != ?"
        params.append(exclude_jadwal_id)
    return db.execute(sql, tuple(params)).fetchall()


def cek_constraint_pilihan(
    matkul: Dict[str, Any],
    ruang: Dict[str, Any],
    slot: Dict[str, Any],
    jadwal_aktif: List[Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    alasan = []

    jumlah_mahasiswa = int(matkul["jumlah_mahasiswa"])
    kapasitas_ruang = int(ruang["kapasitas"])

    if jumlah_mahasiswa > kapasitas_ruang:
        alasan.append(
            f"Kapasitas ruangan tidak mencukupi. Mata kuliah {matkul['nama_matkul']} berisi "
            f"{jumlah_mahasiswa} mahasiswa, sedangkan {ruang['nama_ruang']} hanya berkapasitas "
            f"{kapasitas_ruang} mahasiswa."
        )

    if matkul["kebutuhan_ruang"] == "laboratorium" and ruang["jenis_ruang"] != "laboratorium":
        alasan.append(
            f"Jenis ruangan tidak sesuai. Mata kuliah {matkul['nama_matkul']} membutuhkan laboratorium, "
            f"tetapi ruangan yang dipilih adalah {ruang['nama_ruang']} dengan jenis {ruang['jenis_ruang']}."
        )

    for j in jadwal_aktif:
        if not j.get("kode_slot"):
            continue

        slot_lama = {
            "hari": j["hari"],
            "jam_mulai": j["jam_mulai"],
            "jam_selesai": j["jam_selesai"],
        }

        if j["kode_ruang"] == ruang["kode_ruang"] and waktu_overlap(slot_lama, slot):
            alasan.append(
                f"Bentrok ruangan. {ruang['nama_ruang']} sudah digunakan untuk mata kuliah "
                f"{j['nama_matkul']} pada {j['hari']} pukul {j['jam_mulai']} sampai {j['jam_selesai']}."
            )

        if j["nip"] == matkul["nip"] and waktu_overlap(slot_lama, slot):
            alasan.append(
                f"Bentrok dosen. Dosen dengan NIP {matkul['nip']} sudah mengajar mata kuliah "
                f"{j['nama_matkul']} pada {j['hari']} pukul {j['jam_mulai']} sampai {j['jam_selesai']}."
            )

        if j["kelas"] == matkul["kelas"] and waktu_overlap(slot_lama, slot):
            alasan.append(
                f"Bentrok kelas mahasiswa. Kelas {matkul['kelas']} sudah memiliki jadwal mata kuliah "
                f"{j['nama_matkul']} pada {j['hari']} pukul {j['jam_mulai']} sampai {j['jam_selesai']}."
            )

    return len(alasan) == 0, alasan


def hitung_skor_rekomendasi(
    matkul: Dict[str, Any],
    ruang: Dict[str, Any],
    slot: Dict[str, Any],
    ruang_awal: Optional[Dict[str, Any]] = None,
    slot_awal: Optional[Dict[str, Any]] = None,
) -> int:
    skor = 0

    sisa_kapasitas = int(ruang["kapasitas"]) - int(matkul["jumlah_mahasiswa"])
    skor += max(sisa_kapasitas, 0)

    if matkul["kebutuhan_ruang"] == "kelas" and ruang["jenis_ruang"] == "laboratorium":
        skor += 15

    if matkul["jenis_kegiatan"] == "praktikum" and ruang["jenis_ruang"] == "laboratorium":
        skor -= 5

    if ruang_awal and ruang["kode_ruang"] != ruang_awal["kode_ruang"]:
        skor += 5

    if slot_awal:
        if slot["hari"] != slot_awal["hari"]:
            skor += 20
        elif slot["kode_slot"] != slot_awal["kode_slot"]:
            skor += 10

    skor += waktu_ke_menit(slot["jam_mulai"]) // 180

    if slot["hari"] == "Jumat":
        skor += 3

    return skor


def cari_rekomendasi_branch_and_bound(
    matkul: Dict[str, Any],
    list_ruang: List[Dict[str, Any]],
    list_slot: List[Dict[str, Any]],
    jadwal_aktif: List[Dict[str, Any]],
    ruang_awal: Optional[Dict[str, Any]] = None,
    slot_awal: Optional[Dict[str, Any]] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    kandidat_valid = []
    best_score = float("inf")

    for ruang in list_ruang:
        for slot in list_slot:
            valid, _ = cek_constraint_pilihan(matkul, ruang, slot, jadwal_aktif)
            if not valid:
                continue

            skor = hitung_skor_rekomendasi(matkul, ruang, slot, ruang_awal, slot_awal)

            if best_score != float("inf") and skor > best_score + 50:
                continue

            if skor < best_score:
                best_score = skor

            perubahan = []
            if ruang_awal and ruang["kode_ruang"] != ruang_awal["kode_ruang"]:
                perubahan.append(f"ruangan diganti dari {ruang_awal['nama_ruang']} ke {ruang['nama_ruang']}")
            elif ruang_awal:
                perubahan.append(f"tetap memakai ruangan {ruang['nama_ruang']}")

            if slot_awal:
                if slot["kode_slot"] != slot_awal["kode_slot"]:
                    perubahan.append(
                        f"waktu diganti dari {slot_awal['hari']} {slot_awal['jam_mulai']} sampai {slot_awal['jam_selesai']} "
                        f"ke {slot['hari']} {slot['jam_mulai']} sampai {slot['jam_selesai']}"
                    )
                else:
                    perubahan.append("tetap memakai waktu pilihan awal")

            detail_perubahan = "; ".join(perubahan) if perubahan else "alternatif memenuhi semua constraint"

            kandidat_valid.append(
                {
                    "kode_matkul": matkul["kode_matkul"],
                    "nama_matkul": matkul["nama_matkul"],
                    "kode_ruang": ruang["kode_ruang"],
                    "nama_ruang": ruang["nama_ruang"],
                    "kode_slot": slot["kode_slot"],
                    "hari": slot["hari"],
                    "jam_mulai": slot["jam_mulai"],
                    "jam_selesai": slot["jam_selesai"],
                    "skor": skor,
                    "alasan": (
                        f"Alternatif valid karena tidak melanggar constraint. {detail_perubahan}. "
                        f"Skor {skor} dihitung dari kapasitas ruangan, jenis ruangan, perubahan ruangan, perubahan waktu, dan preferensi jam."
                    ),
                }
            )

    kandidat_valid.sort(key=lambda x: x["skor"])
    return kandidat_valid[:limit]


# ============================================================
# ADMIN DASHBOARD
# ============================================================


def admin_dashboard() -> None:
    st.title("Dashboard Admin")
    st.write("Admin menginput data dasar. Dosen memilih jadwal sendiri. Admin menyetujui jadwal yang sudah diajukan dosen.")

    db = get_db()
    try:
        metrics = {
            "Dosen": db.execute("SELECT COUNT(*) AS total FROM dosen").fetchone()["total"],
            "Mahasiswa": db.execute("SELECT COUNT(*) AS total FROM mahasiswa").fetchone()["total"],
            "Mata Kuliah": db.execute("SELECT COUNT(*) AS total FROM mata_kuliah").fetchone()["total"],
            "Ruang": db.execute("SELECT COUNT(*) AS total FROM ruang").fetchone()["total"],
            "Slot Waktu": db.execute("SELECT COUNT(*) AS total FROM slot_waktu").fetchone()["total"],
            "Total Jadwal": db.execute("SELECT COUNT(*) AS total FROM jadwal").fetchone()["total"],
            "Menunggu Persetujuan": db.execute("SELECT COUNT(*) AS total FROM jadwal WHERE status_jadwal = 'menunggu_persetujuan'").fetchone()["total"],
            "Final": db.execute("SELECT COUNT(*) AS total FROM jadwal WHERE status_jadwal = 'final'").fetchone()["total"],
            "Bentrok": db.execute("SELECT COUNT(*) AS total FROM jadwal WHERE status_jadwal = 'bentrok'").fetchone()["total"],
        }
    finally:
        db.close()

    rows = [list(metrics.items())[i:i + 3] for i in range(0, len(metrics), 3)]
    for row in rows:
        cols = st.columns(3)
        for col, (label, value) in zip(cols, row):
            col.metric(label, value)


# ============================================================
# ADMIN KELOLA DATA
# ============================================================


def admin_tambah_dosen() -> None:
    with st.form("form_tambah_dosen", clear_on_submit=True):
        st.subheader("Tambah Dosen")
        nip = st.text_input("NIP Dosen")
        nama_dosen = st.text_input("Nama Dosen")
        email = st.text_input("Email")
        submit = st.form_submit_button("Simpan Dosen")

    if submit:
        def action(db: Database) -> None:
            db.execute(
                "INSERT INTO dosen (nip, nama_dosen, email, status) VALUES (?, ?, ?, 'aktif')",
                (nip, nama_dosen, email),
            )
            db.execute(
                "INSERT IGNORE INTO users (username, password, role, ref_id) VALUES (?, 'dosen123', 'dosen', ?)",
                (nip.lower(), nip),
            )

        run_write(action, "Data dosen berhasil ditambahkan. Akun dosen otomatis dibuat.", "NIP dosen sudah ada.")


def admin_tambah_mahasiswa() -> None:
    with st.form("form_tambah_mahasiswa", clear_on_submit=True):
        st.subheader("Tambah Mahasiswa")
        nim = st.text_input("NIM")
        nama_mahasiswa = st.text_input("Nama Mahasiswa")
        email = st.text_input("Email")
        semester = st.number_input("Semester", min_value=1, max_value=14, step=1)
        kelas = st.text_input("Kelas", placeholder="Contoh TI-2A")
        submit = st.form_submit_button("Simpan Mahasiswa")

    if submit:
        def action(db: Database) -> None:
            db.execute(
                "INSERT INTO mahasiswa (nim, nama_mahasiswa, email, semester, kelas, status) VALUES (?, ?, ?, ?, ?, 'aktif')",
                (nim, nama_mahasiswa, email, int(semester), kelas),
            )
            db.execute(
                "INSERT IGNORE INTO users (username, password, role, ref_id) VALUES (?, 'mhs123', 'mahasiswa', ?)",
                (nim, kelas),
            )

        run_write(action, "Data mahasiswa berhasil ditambahkan. Akun mahasiswa otomatis dibuat.", "NIM mahasiswa sudah ada.")


def admin_tambah_matkul() -> None:
    dosen = fetch_all("SELECT * FROM dosen ORDER BY nip")
    dosen_options = {f"{d['nip']} - {d['nama_dosen']}": d["nip"] for d in dosen}

    with st.form("form_tambah_matkul", clear_on_submit=True):
        st.subheader("Tambah Mata Kuliah")
        kode_matkul = st.text_input("Kode Matkul")
        nama_matkul = st.text_input("Nama Matkul")
        label_dosen = st.selectbox("Dosen Pengampu", list(dosen_options.keys()) if dosen_options else ["Belum ada dosen"])
        kelas = st.text_input("Kelas")
        semester = st.number_input("Semester", min_value=1, max_value=14, step=1, key="semester_matkul")
        jumlah_mahasiswa = st.number_input("Jumlah Mahasiswa", min_value=1, step=1)
        durasi = st.number_input("Durasi Jam", min_value=1, step=1)
        jenis_kegiatan = st.selectbox("Jenis Kegiatan", ["teori", "praktikum"])
        kebutuhan_ruang = st.selectbox("Kebutuhan Ruang", ["kelas", "laboratorium"])
        submit = st.form_submit_button("Simpan Mata Kuliah")

    if submit:
        if not dosen_options:
            st.error("Data dosen masih kosong.")
            return

        def action(db: Database) -> None:
            db.execute(
                """
                INSERT INTO mata_kuliah
                (kode_matkul, nama_matkul, nip, kelas, semester, jumlah_mahasiswa, durasi, jenis_kegiatan, kebutuhan_ruang)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kode_matkul,
                    nama_matkul,
                    dosen_options[label_dosen],
                    kelas,
                    int(semester),
                    int(jumlah_mahasiswa),
                    int(durasi),
                    jenis_kegiatan,
                    kebutuhan_ruang,
                ),
            )

        run_write(action, "Data mata kuliah berhasil ditambahkan.", "Kode mata kuliah sudah ada atau data dosen tidak valid.")


def admin_tambah_ruang() -> None:
    with st.form("form_tambah_ruang", clear_on_submit=True):
        st.subheader("Tambah Ruang")
        kode_ruang = st.text_input("Kode Ruang")
        nama_ruang = st.text_input("Nama Ruang")
        kapasitas = st.number_input("Kapasitas", min_value=1, step=1)
        jenis_ruang = st.selectbox("Jenis Ruang", ["kelas", "laboratorium"])
        lokasi = st.text_input("Lokasi")
        submit = st.form_submit_button("Simpan Ruang")

    if submit:
        def action(db: Database) -> None:
            db.execute(
                "INSERT INTO ruang (kode_ruang, nama_ruang, kapasitas, jenis_ruang, lokasi, status) VALUES (?, ?, ?, ?, ?, 'aktif')",
                (kode_ruang, nama_ruang, int(kapasitas), jenis_ruang, lokasi),
            )

        run_write(action, "Data ruang berhasil ditambahkan.", "Kode ruang sudah ada.")


def admin_tambah_slot() -> None:
    with st.form("form_tambah_slot", clear_on_submit=True):
        st.subheader("Tambah Slot Waktu")
        kode_slot = st.text_input("Kode Slot")
        hari = st.selectbox("Hari", ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"])
        jam_mulai = st.text_input("Jam Mulai", placeholder="08:00")
        jam_selesai = st.text_input("Jam Selesai", placeholder="10:00")
        submit = st.form_submit_button("Simpan Slot")

    if submit:
        def action(db: Database) -> None:
            db.execute(
                "INSERT INTO slot_waktu (kode_slot, hari, jam_mulai, jam_selesai) VALUES (?, ?, ?, ?)",
                (kode_slot, hari, jam_mulai, jam_selesai),
            )

        run_write(action, "Data slot waktu berhasil ditambahkan.", "Kode slot sudah ada.")


def hapus_data(jenis: str, kode: str) -> None:
    daftar_tabel = {
        "dosen": ("dosen", "nip"),
        "mahasiswa": ("mahasiswa", "nim"),
        "matkul": ("mata_kuliah", "kode_matkul"),
        "ruang": ("ruang", "kode_ruang"),
        "slot": ("slot_waktu", "kode_slot"),
    }

    if jenis not in daftar_tabel:
        st.error("Jenis data tidak valid.")
        return

    tabel, kolom = daftar_tabel[jenis]

    def action(db: Database) -> None:
        db.execute(f"DELETE FROM {tabel} WHERE {kolom} = ?", (kode,))

    run_write(action, "Data berhasil dihapus.", "Data tidak dapat dihapus karena masih digunakan di jadwal.")


def delete_section(label: str, rows: List[Dict[str, Any]], key_field: str, jenis: str, label_func) -> None:
    if not rows:
        return
    with st.expander(f"Hapus {label}"):
        options = {label_func(row): row[key_field] for row in rows}
        selected = st.selectbox(f"Pilih {label}", list(options.keys()), key=f"hapus_{jenis}")
        if st.button(f"Hapus {label}", key=f"btn_hapus_{jenis}", type="secondary"):
            hapus_data(jenis, options[selected])
            rerun_app()


def admin_data() -> None:
    st.title("Kelola Data Sistem")
    tabs = st.tabs(["Tambah Data", "Lihat Data", "Hapus Data"])

    with tabs[0]:
        c1, c2 = st.columns(2)
        with c1:
            admin_tambah_dosen()
            admin_tambah_matkul()
            admin_tambah_slot()
        with c2:
            admin_tambah_mahasiswa()
            admin_tambah_ruang()

    dosen = fetch_all("SELECT * FROM dosen ORDER BY nip")
    mahasiswa = fetch_all("SELECT * FROM mahasiswa ORDER BY nim")
    matkul = fetch_all(
        """
        SELECT m.*, d.nama_dosen
        FROM mata_kuliah m
        LEFT JOIN dosen d ON m.nip = d.nip
        ORDER BY m.kode_matkul
        """
    )
    ruang = fetch_all("SELECT * FROM ruang ORDER BY kode_ruang")
    slot = fetch_all("SELECT * FROM slot_waktu ORDER BY kode_slot")

    with tabs[1]:
        st.subheader("Data Dosen")
        show_table(dosen)
        st.subheader("Data Mahasiswa")
        show_table(mahasiswa)
        st.subheader("Data Mata Kuliah")
        show_table(matkul)
        st.subheader("Data Ruang")
        show_table(ruang)
        st.subheader("Data Slot Waktu")
        show_table(slot)

    with tabs[2]:
        st.warning("Hapus data hanya jika data belum dipakai pada jadwal.")
        delete_section("Dosen", dosen, "nip", "dosen", lambda d: f"{d['nip']} - {d['nama_dosen']}")
        delete_section("Mahasiswa", mahasiswa, "nim", "mahasiswa", lambda m: f"{m['nim']} - {m['nama_mahasiswa']}")
        delete_section("Mata Kuliah", matkul, "kode_matkul", "matkul", lambda m: f"{m['kode_matkul']} - {m['nama_matkul']}")
        delete_section("Ruang", ruang, "kode_ruang", "ruang", lambda r: f"{r['kode_ruang']} - {r['nama_ruang']}")
        delete_section("Slot Waktu", slot, "kode_slot", "slot", lambda s: f"{s['kode_slot']} - {s['hari']} {s['jam_mulai']} sampai {s['jam_selesai']}")


# ============================================================
# DOSEN
# ============================================================


def dosen_dashboard() -> None:
    st.title("Dashboard Dosen")
    nip = st.session_state.ref_id

    jadwal = fetch_all(
        """
        SELECT
            j.id,
            j.status_jadwal,
            j.keterangan,
            j.skor,
            m.nama_matkul,
            m.kelas,
            r.nama_ruang,
            s.hari,
            s.jam_mulai,
            s.jam_selesai
        FROM jadwal j
        JOIN mata_kuliah m ON j.kode_matkul = m.kode_matkul
        LEFT JOIN ruang r ON j.kode_ruang = r.kode_ruang
        LEFT JOIN slot_waktu s ON j.kode_slot = s.kode_slot
        WHERE j.nip = ?
        ORDER BY FIELD(j.status_jadwal, 'bentrok', 'menunggu_persetujuan', 'final', 'ditolak'), s.hari, s.jam_mulai
        """,
        (nip,),
    )

    st.write("Dosen memilih mata kuliah, ruangan, dan slot waktu. Jika bentrok, sistem menampilkan detail bentrok dan rekomendasi Branch and Bound.")

    if st.button("Pilih Jadwal Mata Kuliah", type="primary"):
        st.session_state.page = "Pilih Jadwal"
        rerun_app()

    st.subheader("Jadwal Saya")
    show_table(jadwal)

    bentrok_rows = [j for j in jadwal if j["status_jadwal"] == "bentrok"]
    if bentrok_rows:
        st.subheader("Jadwal Bentrok")
        for j in bentrok_rows:
            cols = st.columns([3, 2, 2, 1])
            cols[0].write(f"**{j['nama_matkul']}**")
            cols[1].write(j.get("nama_ruang") or "-")
            waktu = f"{j.get('hari') or '-'} {j.get('jam_mulai') or ''} sampai {j.get('jam_selesai') or ''}"
            cols[2].write(waktu)
            if cols[3].button("Lihat", key=f"lihat_rec_{j['id']}"):
                st.session_state.rekomendasi_jadwal_id = j["id"]
                st.session_state.page = "Rekomendasi"
                rerun_app()


def dosen_simpan_jadwal(kode_matkul: str, kode_ruang: str, kode_slot: str) -> None:
    nip = st.session_state.ref_id
    db = get_db()

    try:
        matkul = db.execute("SELECT * FROM mata_kuliah WHERE kode_matkul = ? AND nip = ?", (kode_matkul, nip)).fetchone()
        ruang = db.execute("SELECT * FROM ruang WHERE kode_ruang = ?", (kode_ruang,)).fetchone()
        slot = db.execute("SELECT * FROM slot_waktu WHERE kode_slot = ?", (kode_slot,)).fetchone()

        if matkul is None or ruang is None or slot is None:
            st.error("Data mata kuliah, ruang, atau slot tidak ditemukan.")
            return

        sudah_final = db.execute(
            """
            SELECT * FROM jadwal
            WHERE kode_matkul = ? AND status_jadwal = 'final'
            """,
            (kode_matkul,),
        ).fetchone()

        if sudah_final:
            st.warning("Mata kuliah ini sudah memiliki jadwal final. Hubungi Admin jika ingin mengubahnya.")
            return

        jadwal_lama = db.execute(
            """
            SELECT id FROM jadwal
            WHERE kode_matkul = ? AND status_jadwal IN ('bentrok', 'menunggu_persetujuan', 'ditolak')
            """,
            (kode_matkul,),
        ).fetchall()

        for j in jadwal_lama:
            db.execute("DELETE FROM rekomendasi WHERE jadwal_id = ?", (j["id"],))
            db.execute("DELETE FROM jadwal WHERE id = ?", (j["id"],))

        jadwal_aktif = get_jadwal_aktif(db)
        slot_dipilih = {
            "kode_slot": slot["kode_slot"],
            "hari": slot["hari"],
            "jam_mulai": slot["jam_mulai"],
            "jam_selesai": slot["jam_selesai"],
        }

        valid, alasan_bentrok = cek_constraint_pilihan(matkul, ruang, slot_dipilih, jadwal_aktif)

        if valid:
            skor = hitung_skor_rekomendasi(matkul, ruang, slot_dipilih, ruang, slot_dipilih)
            db.execute(
                """
                INSERT INTO jadwal
                (kode_matkul, nip, kode_ruang, kode_slot, status_jadwal, keterangan, skor)
                VALUES (?, ?, ?, ?, 'menunggu_persetujuan', ?, ?)
                """,
                (
                    kode_matkul,
                    nip,
                    kode_ruang,
                    kode_slot,
                    "Jadwal berhasil dipilih dosen dan menunggu persetujuan admin.",
                    skor,
                ),
            )
            db.commit()
            st.success("Jadwal tidak bentrok. Jadwal berhasil diajukan dan menunggu persetujuan Admin.")
            return

        keterangan = "||".join(alasan_bentrok)
        cursor = db.execute(
            """
            INSERT INTO jadwal
            (kode_matkul, nip, kode_ruang, kode_slot, status_jadwal, keterangan, skor)
            VALUES (?, ?, ?, ?, 'bentrok', ?, NULL)
            """,
            (kode_matkul, nip, kode_ruang, kode_slot, keterangan),
        )
        jadwal_id = cursor.lastrowid

        list_ruang = db.execute("SELECT * FROM ruang WHERE status = 'aktif' ORDER BY kode_ruang").fetchall()
        list_slot = db.execute("SELECT * FROM slot_waktu ORDER BY kode_slot").fetchall()
        rekomendasi = cari_rekomendasi_branch_and_bound(matkul, list_ruang, list_slot, jadwal_aktif, ruang, slot_dipilih, limit=5)

        for rec in rekomendasi:
            db.execute(
                """
                INSERT INTO rekomendasi
                (jadwal_id, kode_matkul, kode_ruang, kode_slot, alasan, skor, status)
                VALUES (?, ?, ?, ?, ?, ?, 'tersedia')
                """,
                (
                    jadwal_id,
                    kode_matkul,
                    rec["kode_ruang"],
                    rec["kode_slot"],
                    rec["alasan"],
                    rec["skor"],
                ),
            )

        db.commit()
        st.session_state.rekomendasi_jadwal_id = jadwal_id
        st.session_state.page = "Rekomendasi"
        st.error("Jadwal bentrok. Detail bentrok dan rekomendasi alternatif sudah dibuat.")
        rerun_app()

    except Error as exc:
        db.rollback()
        st.error(f"Terjadi error database: {exc}")
    finally:
        db.close()


def dosen_pilih_jadwal() -> None:
    st.title("Pilih Jadwal Mata Kuliah")
    nip = st.session_state.ref_id

    matkul = fetch_all(
        """
        SELECT m.*, d.nama_dosen
        FROM mata_kuliah m
        JOIN dosen d ON m.nip = d.nip
        WHERE m.nip = ?
        ORDER BY m.kode_matkul
        """,
        (nip,),
    )
    ruang = fetch_all("SELECT * FROM ruang WHERE status = 'aktif' ORDER BY kode_ruang")
    slot = fetch_all("SELECT * FROM slot_waktu ORDER BY kode_slot")

    if not matkul:
        st.warning("Belum ada mata kuliah untuk dosen ini.")
        return
    if not ruang or not slot:
        st.warning("Data ruang atau slot waktu masih kosong.")
        return

    matkul_options = {
        f"{m['kode_matkul']} - {m['nama_matkul']} | Kelas {m['kelas']} | {m['jumlah_mahasiswa']} mahasiswa | {m['kebutuhan_ruang']}": m["kode_matkul"]
        for m in matkul
    }
    ruang_options = {
        f"{r['kode_ruang']} - {r['nama_ruang']} | {r['jenis_ruang']} | kapasitas {r['kapasitas']}": r["kode_ruang"]
        for r in ruang
    }
    slot_options = {
        f"{s['kode_slot']} - {s['hari']}, {s['jam_mulai']} sampai {s['jam_selesai']}": s["kode_slot"]
        for s in slot
    }

    with st.form("form_pilih_jadwal"):
        pilih_matkul = st.selectbox("Mata Kuliah", list(matkul_options.keys()))
        pilih_ruang = st.selectbox("Ruangan", list(ruang_options.keys()))
        pilih_slot = st.selectbox("Slot Waktu", list(slot_options.keys()))
        submit = st.form_submit_button("Simpan Jadwal", type="primary")

    if submit:
        dosen_simpan_jadwal(
            matkul_options[pilih_matkul],
            ruang_options[pilih_ruang],
            slot_options[pilih_slot],
        )

    st.subheader("Riwayat Jadwal Saya")
    jadwal_saya = fetch_all(
        """
        SELECT j.*, m.nama_matkul, r.nama_ruang, s.hari, s.jam_mulai, s.jam_selesai
        FROM jadwal j
        JOIN mata_kuliah m ON j.kode_matkul = m.kode_matkul
        LEFT JOIN ruang r ON j.kode_ruang = r.kode_ruang
        LEFT JOIN slot_waktu s ON j.kode_slot = s.kode_slot
        WHERE j.nip = ?
        ORDER BY j.id DESC
        """,
        (nip,),
    )
    show_table(jadwal_saya)


def dosen_pilih_rekomendasi(rekomendasi_id: int) -> None:
    nip = st.session_state.ref_id
    db = get_db()
    try:
        rec = db.execute(
            """
            SELECT rec.*, j.nip
            FROM rekomendasi rec
            JOIN jadwal j ON rec.jadwal_id = j.id
            WHERE rec.id = ? AND j.nip = ?
            """,
            (rekomendasi_id, nip),
        ).fetchone()

        if rec is None:
            st.error("Rekomendasi tidak ditemukan atau bukan milik dosen ini.")
            return

        db.execute(
            """
            UPDATE jadwal
            SET kode_ruang = ?,
                kode_slot = ?,
                status_jadwal = 'menunggu_persetujuan',
                keterangan = 'Dosen memilih rekomendasi alternatif. Menunggu persetujuan Admin.',
                skor = ?
            WHERE id = ?
            """,
            (rec["kode_ruang"], rec["kode_slot"], rec["skor"], rec["jadwal_id"]),
        )
        db.execute("UPDATE rekomendasi SET status = 'tidak_dipilih' WHERE jadwal_id = ?", (rec["jadwal_id"],))
        db.execute("UPDATE rekomendasi SET status = 'diajukan' WHERE id = ?", (rekomendasi_id,))
        db.commit()
        st.success("Rekomendasi dipilih dan diajukan ke Admin.")
    except Error as exc:
        db.rollback()
        st.error(f"Terjadi error database: {exc}")
    finally:
        db.close()


def dosen_rekomendasi() -> None:
    st.title("Informasi Bentrok dan Rekomendasi")
    nip = st.session_state.ref_id

    if st.session_state.rekomendasi_jadwal_id is None:
        bentrok_rows = fetch_all(
            """
            SELECT j.id, m.nama_matkul, m.kelas, r.nama_ruang, s.hari, s.jam_mulai, s.jam_selesai
            FROM jadwal j
            JOIN mata_kuliah m ON j.kode_matkul = m.kode_matkul
            LEFT JOIN ruang r ON j.kode_ruang = r.kode_ruang
            LEFT JOIN slot_waktu s ON j.kode_slot = s.kode_slot
            WHERE j.nip = ? AND j.status_jadwal = 'bentrok'
            ORDER BY j.id DESC
            """,
            (nip,),
        )
        if not bentrok_rows:
            st.info("Tidak ada jadwal bentrok.")
            return
        selected = st.selectbox(
            "Pilih jadwal bentrok",
            {f"{j['id']} - {j['nama_matkul']} - {j['kelas']}": j["id"] for j in bentrok_rows},
        )
        st.session_state.rekomendasi_jadwal_id = selected

    jadwal_id = st.session_state.rekomendasi_jadwal_id
    db = get_db()
    try:
        jadwal = db.execute(
            """
            SELECT
                j.*,
                m.nama_matkul,
                m.kelas,
                r.nama_ruang,
                s.hari,
                s.jam_mulai,
                s.jam_selesai
            FROM jadwal j
            JOIN mata_kuliah m ON j.kode_matkul = m.kode_matkul
            LEFT JOIN ruang r ON j.kode_ruang = r.kode_ruang
            LEFT JOIN slot_waktu s ON j.kode_slot = s.kode_slot
            WHERE j.id = ? AND j.nip = ?
            """,
            (jadwal_id, nip),
        ).fetchone()

        rekomendasi = db.execute(
            """
            SELECT
                rec.*,
                r.nama_ruang,
                r.jenis_ruang,
                r.kapasitas,
                s.hari,
                s.jam_mulai,
                s.jam_selesai
            FROM rekomendasi rec
            JOIN ruang r ON rec.kode_ruang = r.kode_ruang
            JOIN slot_waktu s ON rec.kode_slot = s.kode_slot
            WHERE rec.jadwal_id = ?
            ORDER BY rec.skor ASC
            """,
            (jadwal_id,),
        ).fetchall()
    finally:
        db.close()

    if jadwal is None:
        st.error("Jadwal tidak ditemukan atau bukan milik dosen ini.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mata Kuliah", jadwal["nama_matkul"])
    c2.metric("Kelas", jadwal["kelas"])
    c3.metric("Ruang Dipilih", jadwal.get("nama_ruang") or "-")
    waktu = f"{jadwal.get('hari') or '-'} {jadwal.get('jam_mulai') or ''} sampai {jadwal.get('jam_selesai') or ''}"
    c4.metric("Waktu Dipilih", waktu)

    st.subheader("Detail Bentrok")
    raw_keterangan = jadwal.get("keterangan") or ""
    bentrok_list = [item.strip() for item in raw_keterangan.split("||") if item.strip()]
    if not bentrok_list:
        bentrok_list = [raw_keterangan] if raw_keterangan else []

    for index, item in enumerate(bentrok_list, start=1):
        st.error(f"{index}. {item}")

    st.subheader("Rekomendasi Alternatif Berdasarkan Branch and Bound")
    if not rekomendasi:
        st.warning("Tidak ada rekomendasi valid. Admin perlu menambah ruang atau slot waktu baru.")
        return

    show_table(rekomendasi)

    st.write("Pilih salah satu rekomendasi yang masih berstatus tersedia.")
    for r in rekomendasi:
        with st.expander(f"Rekomendasi {r['id']} - {r['nama_ruang']} - {r['hari']} {r['jam_mulai']} sampai {r['jam_selesai']} | Skor {r['skor']}"):
            st.write(r["alasan"])
            st.write(f"Status: **{r['status']}**")
            if r["status"] == "tersedia":
                if st.button("Pilih Rekomendasi Ini", key=f"pilih_rec_{r['id']}", type="primary"):
                    dosen_pilih_rekomendasi(r["id"])
                    st.session_state.page = "Dashboard Dosen"
                    rerun_app()


# ============================================================
# ADMIN JADWAL
# ============================================================


def approve_jadwal(jadwal_id: int) -> None:
    def action(db: Database) -> None:
        jadwal = db.execute("SELECT * FROM jadwal WHERE id = ?", (jadwal_id,)).fetchone()
        if jadwal is None:
            raise IntegrityError("Jadwal tidak ditemukan")
        db.execute(
            """
            UPDATE jadwal
            SET status_jadwal = 'final',
                keterangan = 'Jadwal sudah disetujui Admin dan menjadi jadwal final.'
            WHERE id = ?
            """,
            (jadwal_id,),
        )
        db.execute("UPDATE rekomendasi SET status = 'dipilih' WHERE jadwal_id = ? AND status = 'diajukan'", (jadwal_id,))

    run_write(action, "Jadwal berhasil disetujui dan menjadi final.", "Jadwal tidak ditemukan.")


def tolak_jadwal(jadwal_id: int) -> None:
    def action(db: Database) -> None:
        db.execute(
            """
            UPDATE jadwal
            SET status_jadwal = 'ditolak',
                keterangan = 'Jadwal ditolak Admin. Dosen perlu memilih jadwal ulang.'
            WHERE id = ? AND status_jadwal = 'menunggu_persetujuan'
            """,
            (jadwal_id,),
        )
        db.execute("UPDATE rekomendasi SET status = 'ditolak' WHERE jadwal_id = ? AND status = 'diajukan'", (jadwal_id,))

    run_write(action, "Jadwal ditolak. Dosen perlu memilih jadwal ulang.")


def admin_jadwal() -> None:
    st.title("Persetujuan Jadwal dari Dosen")
    jadwal = fetch_all(
        """
        SELECT
            j.id,
            j.status_jadwal,
            j.keterangan,
            j.skor,
            m.kode_matkul,
            m.nama_matkul,
            m.kelas,
            m.jumlah_mahasiswa,
            d.nama_dosen,
            r.nama_ruang,
            r.jenis_ruang,
            s.hari,
            s.jam_mulai,
            s.jam_selesai
        FROM jadwal j
        JOIN mata_kuliah m ON j.kode_matkul = m.kode_matkul
        JOIN dosen d ON j.nip = d.nip
        LEFT JOIN ruang r ON j.kode_ruang = r.kode_ruang
        LEFT JOIN slot_waktu s ON j.kode_slot = s.kode_slot
        ORDER BY FIELD(j.status_jadwal, 'menunggu_persetujuan', 'bentrok', 'final', 'ditolak'), s.hari, s.jam_mulai
        """
    )

    rekomendasi = fetch_all(
        """
        SELECT
            rec.id,
            rec.jadwal_id,
            rec.alasan,
            rec.skor,
            rec.status,
            m.nama_matkul,
            d.nama_dosen,
            r.nama_ruang,
            s.hari,
            s.jam_mulai,
            s.jam_selesai
        FROM rekomendasi rec
        JOIN jadwal j ON rec.jadwal_id = j.id
        JOIN mata_kuliah m ON rec.kode_matkul = m.kode_matkul
        JOIN dosen d ON j.nip = d.nip
        JOIN ruang r ON rec.kode_ruang = r.kode_ruang
        JOIN slot_waktu s ON rec.kode_slot = s.kode_slot
        ORDER BY FIELD(rec.status, 'diajukan', 'tersedia', 'dipilih', 'tidak_dipilih'), rec.skor ASC
        """
    )

    st.subheader("Daftar Jadwal")
    show_table(jadwal)

    pending = [j for j in jadwal if j["status_jadwal"] == "menunggu_persetujuan"]
    if pending:
        st.subheader("Aksi Admin")
        for j in pending:
            with st.expander(f"{j['id']} - {j['nama_matkul']} - {j['nama_dosen']} - {j['kelas']}"):
                st.write(f"Ruang: **{j.get('nama_ruang') or '-'}**")
                st.write(f"Waktu: **{j.get('hari') or '-'} {j.get('jam_mulai') or ''} sampai {j.get('jam_selesai') or ''}**")
                st.write(f"Keterangan: {j.get('keterangan') or '-'}")
                c1, c2 = st.columns(2)
                if c1.button("Setujui", key=f"approve_{j['id']}", type="primary"):
                    approve_jadwal(j["id"])
                    rerun_app()
                if c2.button("Tolak", key=f"tolak_{j['id']}"):
                    tolak_jadwal(j["id"])
                    rerun_app()
    else:
        st.info("Tidak ada jadwal yang menunggu persetujuan.")

    st.subheader("Riwayat Rekomendasi")
    show_table(rekomendasi)


# ============================================================
# MAHASISWA
# ============================================================


def mahasiswa_dashboard() -> None:
    st.title("Dashboard Mahasiswa")
    kelas = st.session_state.ref_id
    st.write(f"Kelas: **{kelas}**")

    jadwal = fetch_all(
        """
        SELECT
            m.nama_matkul,
            m.kelas,
            m.semester,
            d.nama_dosen,
            r.nama_ruang,
            r.lokasi,
            s.hari,
            s.jam_mulai,
            s.jam_selesai,
            j.status_jadwal,
            j.keterangan
        FROM jadwal j
        JOIN mata_kuliah m ON j.kode_matkul = m.kode_matkul
        JOIN dosen d ON j.nip = d.nip
        LEFT JOIN ruang r ON j.kode_ruang = r.kode_ruang
        LEFT JOIN slot_waktu s ON j.kode_slot = s.kode_slot
        WHERE m.kelas = ? AND j.status_jadwal = 'final'
        ORDER BY s.hari, s.jam_mulai
        """,
        (kelas,),
    )

    show_table(jadwal, "Belum ada jadwal final untuk kelas ini.")


# ============================================================
# ROUTER STREAMLIT
# ============================================================


def main() -> None:
    init_session()

    if not is_logged_in():
        login_page()
        return

    sidebar_menu()

    role = st.session_state.role
    page = st.session_state.page

    if role == "admin" and page == "Dashboard Admin":
        admin_dashboard()
    elif role == "admin" and page == "Kelola Data":
        admin_data()
    elif role == "admin" and page == "Persetujuan Jadwal":
        admin_jadwal()
    elif role == "dosen" and page == "Dashboard Dosen":
        dosen_dashboard()
    elif role == "dosen" and page == "Pilih Jadwal":
        dosen_pilih_jadwal()
    elif role == "dosen" and page == "Rekomendasi":
        dosen_rekomendasi()
    elif role == "mahasiswa" and page == "Dashboard Mahasiswa":
        mahasiswa_dashboard()
    else:
        st.error("Halaman tidak ditemukan atau role tidak sesuai.")


if __name__ == "__main__":
    main()