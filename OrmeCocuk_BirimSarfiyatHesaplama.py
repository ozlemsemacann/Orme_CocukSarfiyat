import sys
import subprocess

# Eğer openpyxl yoksa, Python arka planda kendi kendine kursun:
try:
    import openpyxl
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])

import streamlit as st
import pandas as pd
from catboost import CatBoostRegressor, Pool
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# -----------------------------------------------------------------------------
# 1. AYARLAR VE DOSYA YÖNETİMİ
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Örme Sarfiyat Tahmini", layout="wide")

current_dir = os.path.dirname(os.path.abspath(__file__))
EXCEL_NAME = "Yuklenenormecocukdosya7.9.xlsx"
MODEL_NAME = "Orme_BirimSarfiyatModel.cbm"

excel_path = os.path.join(current_dir, EXCEL_NAME)
model_path = os.path.join(current_dir, MODEL_NAME)

@st.cache_data
def load_data():
    if not os.path.exists(excel_path):
        st.error(f"❌ Excel dosyası bulunamadı! Lütfen '{EXCEL_NAME}' adında bir dosyayı proje klasörüne yükle.")
        return None
    try:
        return pd.read_excel(excel_path)
    except Exception as e:
        st.error(f"Excel okuma hatası: {e}")
        return None

@st.cache_resource
def load_model():
    if not os.path.exists(model_path):
        st.error(f"❌ Model dosyası bulunamadı! ({MODEL_NAME})")
        return None
    try:
        model = CatBoostRegressor()
        model.load_model(model_path)
        return model
    except Exception as e:
        st.error(f"Model yükleme hatası: {e}")
        return None

df = load_data()
model = load_model()

if df is None or model is None:
    st.stop()

# -----------------------------------------------------------------------------
# MAİL GÖNDERME FONKSİYONU
# -----------------------------------------------------------------------------
def send_notification_email(prediction_result, user_inputs):
    try:
        # Secrets'tan bilgileri çek (Hata verirse secrets eksiktir)
        smtp_server = st.secrets["email"]["smtp_server"]
        port = st.secrets["email"]["port"]
        sender_email = st.secrets["email"]["sender_email"]
        password = st.secrets["email"]["password"]
        receiver_email = "ozlem.semacan@defacto.com"

        # Mail İçeriğini Hazırla
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = f"🔔 Yeni Birim Sarfiyat Hesaplaması - Model: {user_inputs.get('Manuel_Model_Kodu', 'Belirtilmedi')}"

        body = f"""
        Merhaba,
        
        Uygulama üzerinden yeni bir hesaplama yapıldı. Detaylar aşağıdadır:
        
        ------------------------------------------
        🔮 TAHMİN SONUCU: {prediction_result:.3f} kg
        ------------------------------------------
        
        GİRİLEN VERİLER:
        - Manuel Model Kodu: {user_inputs.get('Manuel_Model_Kodu', 'Belirtilmedi')}
        - Departman: {user_inputs.get('Departman', '-')}
        - Model Türü: {user_inputs.get('Model_Turu', '-')}
        - Model Detayı: {user_inputs.get('Model_Detayi', '-')}
        - Fit: {user_inputs.get('Fit', '-')}
        - Asorti: {user_inputs.get('Asorti', '-')}
        - Pastal Türü: {user_inputs.get('Pastal_Turu', '-')}
        - Kumaş Eni: {user_inputs.get('Kumas_Eni', '-')}
        - Kumaş Gramajı: {user_inputs.get('Kumas_Gramaji', '-')}
        - Toplam Asorti: {user_inputs.get('Toplam_Asorti', '-')}
        - Parça Sayısı: {user_inputs.get('Parca_Sayisi', '-')}
        
        Tarih: {datetime.now().strftime("%d-%m-%Y %H:%M:%S")}
        """
        msg.attach(MIMEText(body, 'plain'))

        # Maili Gönder
        server = smtplib.SMTP(smtp_server, port)
        server.starttls()
        server.login(sender_email, password)
        server.send_message(msg)
        server.quit()
        return True
    except KeyError:
        st.error("Mail gönderilemedi: Streamlit 'Secrets' içinde [email] ayarları bulunamadı.")
        return False
    except Exception as e:
        st.error(f"Mail gönderme hatası: {e}")
        return False

# -----------------------------------------------------------------------------
# 2. ARAYÜZ VE FİLTRELEME
# -----------------------------------------------------------------------------
st.title("🧶 Örme Birim Sarfiyat Tahmini")
st.success("✅ Modeli önceden eğittik ve yükledik. Şimdi değerleri gir, tahmini al!")

inputs = {}

# --- MANUEL MODEL KODU ALANI ---
st.subheader("📝 Model Bilgisi")
inputs['Manuel_Model_Kodu'] = st.text_input("Model Kodu Giriniz", placeholder="Örn: TS-12345-ABC")
st.markdown("---")

# ALT FİLTRELER
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📋 Kategori Seçimi")
    secilen_dept = st.selectbox("Departman", sorted(df['Departman'].astype(str).unique()))
    inputs['Departman'] = secilen_dept
    
    df_step1 = df[df['Departman'] == secilen_dept]
    secilen_tur = st.selectbox("Model_Turu", sorted(df_step1['Model_Turu'].astype(str).unique()))
    inputs['Model_Turu'] = secilen_tur
    
    df_step2 = df_step1[df_step1['Model_Turu'] == secilen_tur]
    secilen_detay = st.selectbox("Model_Detayi", sorted(df_step2['Model_Detayi'].astype(str).unique()))
    inputs['Model_Detayi'] = secilen_detay
    
    df_step3 = df_step2[df_step2['Model_Detayi'] == secilen_detay]
    secilen_fit = st.selectbox("Fit", sorted(df_step3['Fit'].astype(str).unique()))
    inputs['Fit'] = secilen_fit
    df_step4 = df_step3[df_step3['Fit'] == secilen_fit]

with col_right:
    st.subheader("⚙️ Teknik Detaylar")
    asorti_list = sorted(df_step4['Asorti'].astype(str).unique())
    if not asorti_list: 
        asorti_list = sorted(df['Asorti'].astype(str).unique())
        
    inputs['Asorti'] = st.selectbox("Asorti", asorti_list)
    inputs['Pastal_Turu'] = st.selectbox("Pastal_Turu", sorted(df['Pastal_Turu'].astype(str).unique()))

    c1, c2 = st.columns(2)
    inputs['Kumas_Eni'] = c1.number_input("Kumas_Eni", 110.0, 200.0, 180.0)
    inputs['Kumas_Gramaji'] = c2.number_input("Kumas_Gramaji", 110.0, 420.0, 150.0)
    
    # -------------------------------------------------------------------------
    # ORTALAMA PARCA SAYISI HESAPLAMA (Anlık Çalışır)
    # -------------------------------------------------------------------------
    mask = (
        (df['Departman'] == inputs['Departman']) &
        (df['Model_Turu'] == inputs['Model_Turu']) &
        (df['Model_Detayi'] == inputs['Model_Detayi']) &
        (df['Fit'] == inputs['Fit']) &
        (df['Pastal_Turu'] == inputs['Pastal_Turu'])
    )
    
    avg_parca = df[mask]['Parca_Sayisi'].mean()
    
    if pd.isna(avg_parca):
        default_parca = 4.0 # Önceki koddaki varsayılan 4.0 değeri kullanıldı
        st.warning("⚠️ Bu kombinasyona ait geçmiş veri bulunamadı. Varsayılan değer atanıyor.")
    else:
        default_parca = float(round(avg_parca))
        # number_input limitleri içinde tut (1.0 ile 13.0 arası)
        default_parca = max(1.0, min(13.0, default_parca))
        st.info(f"💡 Seçtiğiniz kriterlere göre geçmiş ortalama parça sayısı **{default_parca}** olarak hesaplandı.")

    c3, c4 = st.columns(2)
    inputs['Toplam_Asorti'] = c3.number_input("Toplam_Asorti", 6.0, 14.0, 10.0)
    inputs['Parca_Sayisi'] = c4.number_input("Parca_Sayisi", 1.0, 13.0, value=default_parca)

# -----------------------------------------------------------------------------
# 3. HESAPLAMA VE MAİL İŞLEMİ
# -----------------------------------------------------------------------------
st.divider()

if st.button("HESAPLA", type="primary", use_container_width=True):
    try:
        # 1. Tahmin İşlemi
        X_new = pd.DataFrame([inputs])
        
        # Sadece modelin beklediği sütunları seç (Manuel_Model_Kodu dışarıda kalır)
        X_new = X_new[model.feature_names_]  
        
        cat_features = ['Departman', 'Model_Turu', 'Model_Detayi', 'Fit', 'Pastal_Turu', 'Asorti']
        X_new_pool = Pool(X_new, cat_features=cat_features)
        prediction = model.predict(X_new_pool)[0]
        
        st.success(f"🧶 Tahmini Birim Sarfiyat: **{prediction:.3f} kg**")

        # 2. Mail Gönderme İşlemi
        with st.spinner('Bilgilendirme maili gönderiliyor...'):
            basarili = send_notification_email(prediction, inputs)
            if basarili:
                st.info("✉️ Bilgilendirme maili iletildi.")

    except KeyError as e:
        st.error(f"Sütun Hatası: Model {e} isimli bir veri bekliyor ama kodda eksik veya yanlış yazılmış.")
    except Exception as e:
        st.error(f"Hesaplama sırasında hata oluştu: {e}")
