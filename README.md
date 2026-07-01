# TCL Portatif Klima Döngü Aracı

Bu araç `TAC-12CHPB/DM4` gibi TCL portatif klimalarda kompresörü doğrudan kapatıp açmadan hedef sıcaklığı değiştirerek döngü kurmak için hazırlandı.

Varsayılan döngü:

```text
20 dakika 70°F hedef sıcaklık
20 dakika 80°F hedef sıcaklık
tekrar
```

`70°F` yaklaşık `21.1°C`, `80°F` yaklaşık `26.7°C` eder. API Celsius istiyorsa araç otomatik çevirebilir.

## Hızlı Test

Windows PowerShell veya Komut İstemi:

```powershell
py tcl_cycle.py validate --config config.json
py tcl_cycle.py once cooling --config config.json
py tcl_cycle.py once resting --config config.json
```

Mevcut `config.json` gerçek TCL Home AWS backend'i kullanır. `once cooling` ve `once resting` komutları klimaya gerçek komut gönderir.

Sadece log ile deneme yapmak istersen `config.json` içindeki `backend` değerini geçici olarak `mock` yap.

## Lokal Web Panel

CMD komutları yerine lokal browser paneli kullanabilirsin:

```powershell
py web_app.py --config config.json
```

Veya `run_web.bat` dosyasını çift tıkla. Bilgisayarda panel otomatik olarak şu adreste açılır:

```text
http://127.0.0.1:8787/
```

Panel varsayılan olarak `0.0.0.0:8787` üzerinde çalışır, yani aynı Wi-Fi ağına bağlı telefondan da açılabilir. Telefonda kullanman gereken adres panelin üst kısmında `Telefon: http://...:8787/` olarak görünür. Windows Firewall izin sorarsa yerel ağ erişimine izin ver.

Browser sekmesi kontrol panelidir; 20/20 dakika döngüyü arka plandaki Python web server yürütür. Sekmeyi kapatırsan server açık kaldığı sürece döngü devam eder. Bilgisayarı kapatırsan sistem durur.

Web paneldeki şu butonlar gerçek cihaza komut gönderir:

- `Donguyu Baslat`
- `Swing Baslangic`
- `Simdi 70F`
- `Simdi 80F`

`Cihaz Durumu Oku` sadece status okur, sıcaklık veya swing komutu göndermez.

## Sistem Tepsisi ve EXE

CMD penceresi olmadan sistem tepsisinde çalışan uygulama için kaynak modda şunu çalıştırabilirsin:

```powershell
py -m pip install -r requirements.txt
py tray_app.py --config config.json
```

Veya `run_tray.bat` dosyasını çift tıkla.

Tepsi menüsünde şu seçenekler bulunur:

- `Paneli Ac`
- `Donguyu Baslat`
- `Donguyu Durdur`
- `Swing Baslangic`
- `Simdi 70F`
- `Simdi 80F`
- `Cikis`

EXE üretmek için:

```powershell
build_exe.bat
```

Build çıktısı:

```text
dist\TCL-Klima-Panel\TCL-Klima-Panel.exe
```

EXE çift tıklanınca CMD penceresi açılmaz. Sistem tepsisinde `assets/fan.png` ikonundan üretilen fan ikonu görünür ve web panel arka planda başlar. Aynı Wi-Fi ağındaki telefondan panelde gösterilen `Telefon:` adresiyle bağlanabilirsin. `config.json` EXE klasörüne kopyalanır; ayar değiştirmek istersen EXE yanındaki `config.json` dosyasını düzenle.

`TCL_SSO_TOKEN` EXE içine gömülmez. Windows ortam değişkeni olarak kalır.

## Döngüyü Başlatma

```powershell
py tcl_cycle.py run --config config.json
```

Veya `run_cycle.bat` dosyasını çalıştır.

Durdurmak için `Ctrl+C` kullan.

## Gerçek Cihaza Bağlama

`config.json` içindeki `backend` alanı gerçek TCL Home bağlantısı için hazırdır:

```json
"backend": "tcl_home_aws"
```

Alternatif backend kullanmak istersen şu değerlerden birine değiştirebilirsin:

```json
"backend": "home_assistant"
```

veya:

```json
"backend": "tcl_home_aws"
```

veya:

```json
"backend": "tuya_cloud"
```

### TCL Home AWS

Bu modelde TCL Home, cihaz komutlarını AWS IoT Shadow ile gönderiyor.

Yakalanan komut endpointi:

```text
https://data.iot.eu-central-1.amazonaws.com/topics/%24aws/things/DWG42RFAAAE/shadow/update?qos=1
```

Sıcaklık komut payloadları:

```json
{
  "state": {
    "desired": {
      "targetCelsiusDegree": 21,
      "targetFahrenheitDegree": 70
    }
  }
}
```

```json
{
  "state": {
    "desired": {
      "targetCelsiusDegree": 26,
      "targetFahrenheitDegree": 80
    }
  }
}
```

Gerçek cihaza bağlanmak için `config.json` içinde şunu değiştir:

```json
"backend": "tcl_home_aws"
```

Sonra TCL Home trafiğindeki şu isteği bul:

```text
GET https://eu-iot-api-prod.tcljd.com/v1/auth/service/loadBalance
```

Bu request header içindeki `ssotoken` değerini yerel ortam değişkeni olarak kaydet:

```powershell
setx TCL_SSO_TOKEN "BURAYA_HTTP_TOOLKITTEKI_SSOTOKEN"
```

Yeni PowerShell penceresi açtıktan sonra önce status dene:

```powershell
py tcl_cycle.py status --config config.json
```

Status çalışırsa tek komut testleri:

```powershell
py tcl_cycle.py startup --config config.json
py tcl_cycle.py once cooling --config config.json
py tcl_cycle.py once resting --config config.json
```

`startup` komutu swing'i açmak için tek seferlik başlangıç komutu gönderir:

```json
{
  "state": {
    "desired": {
      "swingWind": 1
    }
  }
}
```

`run` komutu başladığında bu başlangıç komutunu bir kez gönderir. Sonraki `70°F` ve `80°F` sıcaklık komutları swing alanını tekrar göndermez.

Varsayılan olarak sadece `targetCelsiusDegree` ve `targetFahrenheitDegree` gönderilir. Fan hızı, swing veya mod ayarlarını da her komutta zorlamak istersen `send_full_state` değerini `true` yapabilirsin.

Komut gönderimi varsayılan olarak AWS IoT MQTT-over-WebSocket ile yapılır:

```json
"command_method": "mqtt_ws"
```

REST Shadow update denemek istersen:

```json
"command_method": "shadow_update"
```

HTTP Toolkit'te yakalanan publish endpointine dönmek gerekirse:

```json
"command_method": "topic_publish"
```

Not: `ssotoken` şifre gibi hassas kabul edilmeli. Chat'e veya ekran görüntüsüne koyma. Süresi dolarsa TCL Home'u HTTP Toolkit ile açıp yeni `ssotoken` alman gerekir.

### Home Assistant

Klima Home Assistant içinde `climate` entity olarak görünüyorsa en temiz yol budur.

Gerekli alanlar:

```json
"home_assistant": {
  "base_url": "http://homeassistant.local:8123",
  "token": "${HA_TOKEN}",
  "entity_id": "climate.tcl_portatif_klima",
  "temperature_unit": "F"
}
```

Windows ortam değişkeni örneği:

```powershell
setx HA_TOKEN "BURAYA_HOME_ASSISTANT_LONG_LIVED_TOKEN"
```

Yeni terminal açtıktan sonra test et:

```powershell
py tcl_cycle.py status --config config.json
```

### Tuya Cloud

Cihaz Smart Life veya Tuya Smart tarafına eklenebiliyorsa Tuya Cloud ile denenebilir.

Gerekli ortam değişkenleri:

```powershell
setx TUYA_ACCESS_ID "..."
setx TUYA_ACCESS_SECRET "..."
setx TUYA_DEVICE_ID "..."
```

Yeni terminal açtıktan sonra:

```powershell
py tcl_cycle.py status --config config.json
```

Tuya cihazlarında komut kodları modelden modele değişebilir. `config.json` içindeki şu bölüm gerekirse güncellenir:

```json
"commands": {
  "mode": {
    "code": "mode",
    "cool_value": "cold"
  },
  "temperature": {
    "code": "temp_set",
    "unit": "C",
    "scale": 1,
    "value_type": "integer"
  },
  "fan": {
    "code": "fan_speed_enum",
    "value": "auto"
  }
}
```

## Notlar

- Araç klimayı kapatmaz; sadece hedef sıcaklığı `70°F` ve `80°F` arasında değiştirir.
- Oda sıcaklığı `80°F` üstündeyse dinlenme fazında bile kompresör çalışabilir. Bu termostat davranışıdır.
- `logs/tcl_cycle.log` dosyasına çalışma logları yazılır.
- TCL Home doğrudan kapalı/proprietary API kullanıyorsa ayrıca TCL Home trafiğini veya desteklediği entegrasyonu tespit etmek gerekir.
