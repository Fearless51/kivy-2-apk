import json
import os
import time
import threading
from datetime import datetime

import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.utils import get_color_from_hex
from kivy.graphics import Color, Line, Ellipse, Rectangle
from kivy.core.text import Label as CoreLabel
from kivy.clock import Clock

# Masaüstü testi için boyutlandırma (Android'de otomatik tam ekran olur)
Window.size = (1100, 680)
Window.clearcolor = get_color_from_hex("#f8f9fa")

class Ders:
    def __init__(self, ders_adi, katsayi=1.0):
        self.ders_adi = ders_adi
        self.katsayi = katsayi

    def net_hesapla(self, dogru, yanlis):
        net_sonucu = dogru - (yanlis / 3)
        return max(0.0, round(net_sonucu, 2))


# --- 📈 NOKTA ÜZERİNE YAZI KAZIYAN ÇİFT MODLU GELİŞMİŞ GRAFİK MOTORU ---
class SadeGrafikCizici(BoxLayout):
    def __init__(self, gecmis, **kwargs):
        super().__init__(**kwargs)
        self.gecmis = gecmis
        self.mod = "puan"
        self.bind(size=self.grafik_yeniden_ciz, pos=self.grafik_yeniden_ciz)

    def grafik_yeniden_ciz(self, *args):
        self.canvas.clear()
        if not self.gecmis:
            return

        pad_left = 80
        pad_right = 80
        pad_bottom = 60
        pad_top = 70
        
        w_grafik = self.width - (pad_left + pad_right)
        h_grafik = self.height - (pad_bottom + pad_top)

        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(pos=(self.x + pad_left, self.y + pad_bottom), size=(w_grafik, h_grafik))
            
            Color(0.3, 0.3, 0.3, 1)
            Line(points=[self.x + pad_left, self.y + pad_bottom, self.x + pad_left, self.y + pad_bottom + h_grafik], width=2)
            Line(points=[self.x + pad_left, self.y + pad_bottom, self.x + pad_left + w_grafik, self.y + pad_bottom], width=2)

        if self.mod == "puan":
            degerler = [s["lgs_puani_500"] for s in self.gecmis]
            min_deger = 195
            maks_deger = max(500, max(degerler)) if degerler else 500
            cizgi_renk = (0, 0.45, 0.9, 1)
        else:
            degerler = [s["toplam_net"] for s in self.gecmis]
            min_deger = 0
            maks_deger = max(90, max(degerler)) if degerler else 90
            cizgi_renk = (0.15, 0.65, 0.27, 1)

        n = len(degerler)
        adim_x = w_grafik / (n - 1) if n > 1 else w_grafik
        aralik = (maks_deger - min_deger) if (maks_deger - min_deger) != 0 else 1

        noktalar = []
        for i, val in enumerate(degerler):
            nx = self.x + pad_left + (i * adim_x)
            ny = self.y + pad_bottom + (((val - min_deger) / aralik) * h_grafik)
            noktalar.append((nx, ny, val, self.gecmis[i]["sınav_adı"]))

        with self.canvas:
            Color(*cizgi_renk)
            if n > 1:
                flat_points = []
                for pt in noktalar:
                    flat_points.extend([pt[0], pt[1]])
                Line(points=flat_points, width=3)

            for pt in noktalar:
                nx, ny, val, isim = pt
                Color(0.9, 0.1, 0.1, 1)
                Ellipse(pos=(nx - 6, ny - 6), size=(12, 12))
                
                # Çakışmayı önleyen akıllı etiketler
                etiket_metni = f"{isim}\n({val})"
                core_lbl = CoreLabel(text=etiket_metni, font_size=11, bold=True)
                core_lbl.refresh()
                text_texture = core_lbl.texture
                
                Color(0.1, 0.1, 0.1, 1)
                Rectangle(
                    texture=text_texture, 
                    pos=(nx - text_texture.width / 2, ny + 14), 
                    size=text_texture.size
                )


class CanavarLGSSadeCrossApp(App):
    def build(self):
        self.title = "LGS Deneme Takip Sistemi v11.0"
        
        # Dosya yolunu Android uyumlu yapıyoruz (Çökme engelleme)
        if kivy.platform == 'android':
            from android.storage import app_storage_dir
            self.dosya_adi = os.path.join(app_storage_dir(), "deneme_sonuclari.json")
        else:
            self.dosya_adi = "deneme_sonuclari.json"
        
        # Sayaç Değişkenleri
        self.calisma_saniyesi = 25 * 60
        self.mola_saniyesi = 5 * 60
        self.kalan_sure = self.calisma_saniyesi
        self.sayac_modu = "calisma"
        self.sayac_calisiyor = False

        self.ders_tanimlari = {
            "Türkçe": Ders("Türkçe", katsayi=4.0),
            "Matematik": Ders("Matematik", katsayi=4.0),
            "Fen Bilimleri": Ders("Fen Bilimleri", katsayi=4.0),
            "T.C. İnkılap": Ders("T.C. İnkılap Tarihi", katsayi=1.0),
            "Din Kültürü": Ders("Din Kültürü", katsayi=1.0),
            "Yabancı Dil": Ders("Yabancı Dil", katsayi=1.0)
        }
        
        self.verileri_yukle()
        
        # --- ANA DÜZEN ---
        ana_layout = BoxLayout(orientation='vertical', padding=15, spacing=10)
        
        # --- 🕒 GERİ SAYIM PANELİ ---
        sayac_paneli = BoxLayout(orientation='horizontal', size_hint_y=None, height=65, spacing=15)
        
        lgs_kutu = BoxLayout(orientation='vertical', padding=5)
        with lgs_kutu.canvas.before:
            Color(0.9, 0.95, 1, 1)
            self.rect_lgs = Rectangle(pos=lgs_kutu.pos, size=lgs_kutu.size)
        lgs_kutu.bind(pos=self._update_rect_lgs, size=self._update_rect_lgs)
        
        self.lbl_lgs_sayac = Label(text="LGS Sayaç...", color=get_color_from_hex("#004085"), font_size="13sp", bold=True, halign="center")
        lgs_kutu.add_widget(self.lbl_lgs_sayac)
        
        yks_kutu = BoxLayout(orientation='vertical', padding=5)
        with yks_kutu.canvas.before:
            Color(0.93, 0.98, 0.93, 1)
            self.rect_yks = Rectangle(pos=yks_kutu.pos, size=yks_kutu.size)
        yks_kutu.bind(pos=self._update_rect_yks, size=self._update_rect_yks)
        
        self.lbl_yks_sayac = Label(text="YKS Sayaç...", color=get_color_from_hex("#155724"), font_size="13sp", bold=True, halign="center")
        yks_kutu.add_widget(self.lbl_yks_sayac)
        
        sayac_paneli.add_widget(lgs_kutu)
        sayac_paneli.add_widget(yks_kutu)
        ana_layout.add_widget(sayac_paneli)
        
        # --- ORTALAMALAR ---
        ust_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=45, spacing=10)
        self.lbl_ort_sinav = Label(text="Toplam Sınav: 0", color=get_color_from_hex("#495057"), bold=True)
        self.lbl_ort_net = Label(text="Net Ortalaması: 0.0", color=get_color_from_hex("#385723"), bold=True)
        self.lbl_ort_puan = Label(text="Puan Ortalaması: 0.0", color=get_color_from_hex("#c65911"), bold=True)
        ust_bar.add_widget(self.lbl_ort_sinav)
        ust_bar.add_widget(self.lbl_ort_net)
        ust_bar.add_widget(self.lbl_ort_puan)
        ana_layout.add_widget(ust_bar)
        
        # --- ORTA ALAN ---
        orta_panel = BoxLayout(orientation='horizontal', spacing=15)
        
        # SOL PANEL: VERİ GİRİŞİ
        sol_panel = BoxLayout(orientation='vertical', size_hint_x=0.4, spacing=8, padding=10)
        sol_panel.add_widget(Label(text="Sınav Adı:", color=get_color_from_hex("#212529"), size_hint_y=None, height=25))
        self.ent_sinav_adi = TextInput(hint_text="Örn: Özdebir 1", multiline=False, size_hint_y=None, height=35)
        sol_panel.add_widget(self.ent_sinav_adi)
        
        baslik_grid = GridLayout(cols=3, size_hint_y=None, height=30)
        baslik_grid.add_widget(Label(text="Ders", color=get_color_from_hex("#6c757d")))
        baslik_grid.add_widget(Label(text="D", color=get_color_from_hex("#6c757d")))
        baslik_grid.add_widget(Label(text="Y", color=get_color_from_hex("#6c757d")))
        sol_panel.add_widget(baslik_grid)
        
        self.girdi_kutulari = {}
        ders_grid = GridLayout(cols=3, spacing=5)
        for ders in self.ders_tanimlari.keys():
            ders_grid.add_widget(Label(text=ders, color=get_color_from_hex("#212529")))
            ent_d = TextInput(text="0", multiline=False, input_filter="int", halign="center")
            ent_y = TextInput(text="0", multiline=False, input_filter="int", halign="center")
            ders_grid.add_widget(ent_d)
            ders_grid.add_widget(ent_y)
            self.girdi_kutulari[ders] = {"D": ent_d, "Y": ent_y}
        sol_panel.add_widget(ders_grid)
        
        btn_ekle = Button(text="Hesapla ve Listeye Ekle", size_hint_y=None, height=45, background_color=get_color_from_hex("#007bff"), background_normal="")
        btn_ekle.bind(on_release=self.deneme_ekle)
        sol_panel.add_widget(btn_ekle)
        orta_panel.add_widget(sol_panel)
        
        # SAĞ PANEL: TABLO LİSTESİ
        sag_panel = BoxLayout(orientation='vertical', size_hint_x=0.6)
        liste_baslik = BoxLayout(orientation='horizontal', size_hint_y=None, height=30)
        liste_baslik.add_widget(Label(text=" Sınav Bilgisi (Ad | Net | Puan)", color=get_color_from_hex("#495057"), halign="left"))
        sag_panel.add_widget(liste_baslik)
        
        self.scroll_view = ScrollView()
        self.liste_layout = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self.liste_layout.bind(minimum_height=self.liste_layout.setter('height'))
        self.scroll_view.add_widget(self.liste_layout)
        sag_panel.add_widget(self.scroll_view)
        
        # Alt Butonlar
        alt_islem_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=45, spacing=5, padding=[0, 5, 0, 0])
        
        btn_sil = Button(text="🗑️ Sil", background_color=get_color_from_hex("#dc3545"), background_normal="")
        btn_sil.bind(on_release=self.deneme_sil)
        
        btn_grafik = Button(text="📈 Grafik", background_color=get_color_from_hex("#6c757d"), background_normal="")
        btn_grafik.bind(on_release=self.pop_grafik_goster)
        
        btn_koc = Button(text="🤖 AI Koç", background_color=get_color_from_hex("#17a2b8"), background_normal="")
        btn_koc.bind(on_release=self.pop_koc_analizi)
        
        btn_pomo = Button(text="⏱️ Sayaç", background_color=get_color_from_hex("#ffc107"), color=get_color_from_hex("#212529"), background_normal="")
        btn_pomo.bind(on_release=self.pop_sayac_goster)
        
        alt_islem_bar.add_widget(btn_sil)
        alt_islem_bar.add_widget(btn_grafik)
        alt_islem_bar.add_widget(btn_koc)
        alt_islem_bar.add_widget(btn_pomo)
        
        sag_panel.add_widget(alt_islem_bar)
        orta_panel.add_widget(sag_panel)
        ana_layout.add_widget(orta_panel)
        
        self.secili_sınav_index = None
        self.listeyi_yenile()
        
        # Android Uyumlu Saat Güncelleyiciler (Çökmeyi engeller)
        Clock.schedule_interval(self.sinav_sayaclarini_guncelle, 1.0)
        Clock.schedule_interval(self.android_safe_pomodoro, 1.0)
        
        return ana_layout

    def _update_rect_lgs(self, instance, value):
        self.rect_lgs.pos = instance.pos
        self.rect_lgs.size = instance.size
        
    def _update_rect_yks(self, instance, value):
        self.rect_yks.pos = instance.pos
        self.rect_yks.size = instance.size

    def sinav_sayaclarini_guncelle(self, dt):
        simdi = datetime.now()
        lgs_tarih = datetime(2026, 6, 13, 9, 30, 0)
        yks_tarih = datetime(2026, 6, 21, 9, 30, 0)
        
        if lgs_tarih > simdi:
            fark_lgs = lgs_tarih - simdi
            gun = fark_lgs.days
            saat, kalan = divmod(fark_lgs.seconds, 3600)
            dakika, saniye = divmod(kalan, 60)
            self.lbl_lgs_sayac.text = f"🎯 2026 LGS'YE KALAN SÜRE\n{gun} Gün  {saat:02d}:{dakika:02d}:{saniye:02d}"
        else:
            self.lbl_lgs_sayac.text = "🎯 LGS Sınavı Başladı!"

        if yks_tarih > simdi:
            fark_yks = yks_tarih - simdi
            gun = fark_yks.days
            saat, kalan = divmod(fark_yks.seconds, 3600)
            dakika, saniye = divmod(kalan, 60)
            self.lbl_yks_sayac.text = f"🎓 2026 YKS'YE KALAN SÜRE\n{gun} Gün  {saat:02d}:{dakika:02d}:{saniye:02d}"
        else:
            self.lbl_yks_sayac.text = "🎓 YKS Sınavı Başladı!"

    def android_safe_pomodoro(self, dt):
        if self.sayac_calisiyor and self.kalan_sure > 0:
            self.kalan_sure -= 1
            if hasattr(self, 'lbl_sayac_zaman'):
                self.lbl_sayac_zaman.text = self.format_sure(self.kalan_sure)
            
            if self.kalan_sure == 0:
                if self.sayac_modu == "calisma":
                    self.sayac_modu = "mola"
                    self.kalan_sure = self.mola_saniyesi
                    if hasattr(self, 'lbl_sayac_durum'): self.lbl_sayac_durum.text = "MOLA ZAMANI"
                else:
                    self.sayac_modu = "calisma"
                    self.kalan_sure = self.calisma_saniyesi
                    if hasattr(self, 'lbl_sayac_durum'): self.lbl_sayac_durum.text = "ÇALIŞMA ETÜDÜ"
                    self.sayac_calisiyor = False
                    if hasattr(self, 'btn_sayac_kontrol'): 
                        self.btn_sayac_kontrol.text = "Başlat"
                        self.btn_sayac_kontrol.background_color = get_color_from_hex("#28a745")

    def verileri_yukle(self):
        if os.path.exists(self.dosya_adi):
            try:
                with open(self.dosya_adi, "r", encoding="utf-8") as dosya:
                    self.gecmis = json.load(dosya)
            except: self.gecmis = []
        else:
            self.gecmis = []

    def verileri_kaydet(self):
        with open(self.dosya_adi, "w", encoding="utf-8") as dosya:
            json.dump(self.gecmis, dosya, ensure_ascii=False, indent=4)

    def lgs_puani_hesapla(self, agirlikli_puan):
        if agirlikli_puan == 0: return 195.0
        return min(500.0, round(195.0 + (agirlikli_puan * (305.0 / 270.0)), 2))

    def listeyi_yenile(self):
        self.liste_layout.clear_widgets()
        self.secili_sınav_index = None
        toplam_net = 0.0
        toplam_puan = 0.0
        
        for idx, s in enumerate(self.gecmis):
            metin = f"  {idx+1}. {s['sınav_adı']}  |  {s['toplam_net']} Net  |  {s['lgs_puani_500']} Puan"
            satir_btn = Button(text=metin, size_hint_y=None, height=40, halign="left", valign="middle",
                               background_color=get_color_from_hex("#ffffff"), color=get_color_from_hex("#212529"), background_normal="")
            satir_btn.bind(size=satir_btn.setter('text_size'))
            satir_btn.bind(on_release=lambda btn, i=idx: self.sınav_sec(i, btn))
            self.liste_layout.add_widget(satir_btn)
            toplam_net += s["toplam_net"]
            toplam_puan += s["lgs_puani_500"]
            
        if self.gecmis:
            n = len(self.gecmis)
            self.lbl_ort_sinav.text = f"Toplam: {n} Adet"
            self.lbl_ort_net.text = f"Net Ort: {round(toplam_net/n, 2)}"
            self.lbl_ort_puan.text = f"Puan Ort: {round(toplam_puan/n, 2)}"
        else:
            self.lbl_ort_sinav.text = "Toplam: 0"
            self.lbl_ort_net.text = "Net Ort: 0.0"
            self.lbl_ort_puan.text = "Puan Ort: 0.0"

    def sınav_sec(self, index, buton):
        for child in self.liste_layout.children:
            child.background_color = get_color_from_hex("#ffffff")
            child.color = get_color_from_hex("#212529")
        buton.background_color = get_color_from_hex("#007bff")
        buton.color = get_color_from_hex("#ffffff")
        self.secili_sınav_index = index

    def deneme_ekle(self, instance):
        s_adi = self.ent_sinav_adi.text.strip()
        if not s_adi:
            s_adi = f"Deneme ({datetime.now().strftime('%d.%m.%Y')})"
        yeni_sinav = {
            "sınav_adı": s_adi, "tarih": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "dersler": {}, "toplam_net": 0.0, "tahmini_agirlikli_puan": 0.0, "lgs_puani_500": 0.0
        }
        toplam_net = 0.0
        toplam_puan = 0.0
        try:
            for d_adi, ders_obj in self.ders_tanimlari.items():
                d_val = self.girdi_kutulari[d_adi]["D"].text
                y_val = self.girdi_kutulari[d_adi]["Y"].text
                d_sayi = int(d_val) if d_val else 0
                y_sayi = int(y_val) if y_val else 0
                net = ders_obj.net_hesapla(d_sayi, y_sayi)
                toplam_net += net
                toplam_puan += net * ders_obj.katsayi
                yeni_sinav["dersler"][d_adi] = {"Doğru": d_sayi, "Yanlış": y_sayi, "Net": net}
                
            yeni_sinav["toplam_net"] = round(toplam_net, 2)
            yeni_sinav["tahmini_agirlikli_puan"] = round(toplam_puan, 2)
            yeni_sinav["lgs_puani_500"] = self.lgs_puani_hesapla(toplam_puan)
            
            self.gecmis.append(yeni_sinav)
            self.verileri_kaydet()
            self.listeyi_yenile()
            self.ent_sinav_adi.text = ""
            for d_adi in self.ders_tanimlari.keys():
                self.girdi_kutulari[d_adi]["D"].text = "0"
                self.girdi_kutulari[d_adi]["Y"].text = "0"
        except ValueError: pass

    def deneme_sil(self, instance):
        if self.secili_sınav_index is None: return
        self.gecmis.pop(self.secili_sınav_index)
        self.verileri_kaydet()
        self.listeyi_yenile()

    def pop_koc_analizi(self, instance):
        if len(self.gecmis) < 2:
            msg = "Gelişimi görebilmem için en az 2 adet deneme girmelisin kral!"
        else:
            son = self.gecmis[-1]
            onceki = self.gecmis[-2]
            fark = round(son["toplam_net"] - onceki["toplam_net"], 2)
            if fark > 0:
                msg = f"Süper gelişim kral! Son sınavda netlerini {fark} artırdın. Motivasyonu düşürmeden aynen devam!"
            elif fark < 0:
                msg = f"Netlerinde {abs(fark)} kadar ufak bir gerileme olmuş. Hiç moral bozma, eksikleri kapatmak için harika bir fırsat."
            else:
                msg = "Netlerin bir öncekiyle aynı kalmış. Küçük bir tempo artışı seni öne geçirecektir!"

        box = BoxLayout(orientation='vertical', padding=20, spacing=15)
        box.add_widget(Label(text=msg, color=(1, 1, 1, 1), bold=True, halign="center", text_size=(340, None), font_size="14sp"))
        btn_kapat = Button(text="Kapat", size_hint_y=None, height=45, background_color=get_color_from_hex("#17a2b8"), background_normal="")
        box.add_widget(btn_kapat)
        popup = Popup(title="🤖 AI Koç Raporu", content=box, size_hint=(None, None), size=(400, 260))
        btn_kapat.bind(on_release=popup.dismiss)
        popup.open()

    def pop_grafik_goster(self, instance):
        if not self.gecmis: return
        box = BoxLayout(orientation='vertical', padding=10, spacing=10)
        secim_bari = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=10)
        btn_puan_mod = Button(text="📈 LGS Puan Grafiği", background_color=get_color_from_hex("#007bff"), background_normal="", bold=True)
        btn_net_mod = Button(text="📊 Toplam Net Grafiği", background_color=get_color_from_hex("#28a745"), background_normal="", bold=True)
        secim_bari.add_widget(btn_puan_mod)
        secim_bari.add_widget(btn_net_mod)
        box.add_widget(secim_bari)
        
        grafik = SadeGrafikCizici(gecmis=self.gecmis)
        box.add_widget(grafik)
        
        btn_puan_mod.bind(on_release=lambda x: setattr(grafik, 'mod', 'puan') or grafik.grafik_yeniden_ciz())
        btn_net_mod.bind(on_release=lambda x: setattr(grafik, 'mod', 'net') or grafik.grafik_yeniden_ciz())
        
        btn_kapat = Button(text="Grafiği Kapat", size_hint_y=None, height=45, background_color=get_color_from_hex("#6c757d"), background_normal="")
        box.add_widget(btn_kapat)
        popup = Popup(title="📈 LGS Gelişim Grafiği", content=box, size_hint=(0.95, 0.95))
        btn_kapat.bind(on_release=popup.dismiss)
        popup.open()

    def pop_sayac_goster(self, instance):
        box = BoxLayout(orientation='vertical', padding=15, spacing=10)
        durum_metni = "ÇALIŞMA ETÜDÜ" if self.sayac_modu == "calisma" else "MOLA ZAMANI"
        self.lbl_sayac_durum = Label(text=durum_metni, font_size="15sp", bold=True, size_hint_y=None, height=20)
        self.lbl_sayac_zaman = Label(text=self.format_sure(self.kalan_sure), font_size="42sp", bold=True)
        box.add_widget(self.lbl_sayac_durum)
        box.add_widget(self.lbl_sayac_zaman)
        
        girdi_alani = GridLayout(cols=2, spacing=10, size_hint_y=None, height=75)
        girdi_alani.add_widget(Label(text="Çalışma (Dk):", font_size="13sp"))
        girdi_alani.add_widget(Label(text="Mola (Dk):", font_size="13sp"))
        self.ent_calisma_dk = TextInput(text=str(self.calisma_saniyesi // 60), multiline=False, input_filter="int", halign="center")
        self.ent_mola_dk = TextInput(text=str(self.mola_saniyesi // 60), multiline=False, input_filter="int", halign="center")
        girdi_alani.add_widget(self.ent_calisma_dk)
        girdi_alani.add_widget(self.ent_mola_dk)
        box.add_widget(girdi_alani)
        
        self.btn_sayac_kontrol = Button(text="Başlat" if not self.sayac_calisiyor else "Durdur", size_hint_y=None, height=40, 
                                        background_color=get_color_from_hex("#28a745") if not self.sayac_calisiyor else get_color_from_hex("#ffc107"), background_normal="")
        self.btn_sayac_kontrol.bind(on_release=self.sayac_tetikle)
        
        btn_ayar_kaydet = Button(text="Süreleri Sıfırla", size_hint_y=None, height=40, background_color=get_color_from_hex("#007bff"), background_normal="")
        btn_ayar_kaydet.bind(on_release=self.sayac_surelerini_guncelle)
        box.add_widget(self.btn_sayac_kontrol)
        box.add_widget(btn_ayar_kaydet)
        
        self.sayac_popup = Popup(title="⏱️ Çalışma Sayacı", content=box, size_hint=(None, None), size=(360, 360))
        self.sayac_popup.open()

    def format_sure(self, saniye):
        return f"{saniye // 60:02d}:{saniye % 60:02d}"

    def sayac_surelerini_guncelle(self, instance):
        try:
            self.calisma_saniyesi = max(1, int(self.ent_calisma_dk.text)) * 60
            self.mola_saniyesi = max(1, int(self.ent_mola_dk.text)) * 60
            self.sayac_calisiyor = False
            self.sayac_modu = "calisma"
            self.kalan_sure = self.calisma_saniyesi
            self.lbl_sayac_durum.text = "ÇALIŞMA ETÜDÜ"
            self.lbl_sayac_zaman.text = self.format_sure(self.kalan_sure)
            self.btn_sayac_kontrol.text = "Başlat"
            self.btn_sayac_kontrol.background_color = get_color_from_hex("#28a745")
        except: pass

    def sayac_tetikle(self, instance):
        if self.sayac_calisiyor:
            self.sayac_calisiyor = False
            instance.text = "Başlat"
            instance.background_color = get_color_from_hex("#28a745")
        else:
            self.sayac_calisiyor = True
            instance.text = "Durdur"
            instance.background_color = get_color_from_hex("#ffc107")


if __name__ == "__main__":
    CanavarLGSSadeCrossApp().run()
