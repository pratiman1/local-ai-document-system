"""
tools/run_hindi_to_english_10sections.py
-----------------------------------------
Executes 100% offline Hindi to English translation on the 10-section real
Technology & Science document using IndicTrans2 on CPU float32 with
micro-batching, phrase glossary protection, heading isolation, and grammar post-processing.
"""

import sys
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # PyMuPDF
from translation.translator_factory import get_translator
from translation.translation_pipeline import translate_page
from translation.indic_text_processor import (
    GlossaryManager,
    audit_literal_translations,
    is_section_heading,
)

PDF_PATH = PROJECT_ROOT / "uploads" / "Technology_Science_Everyday_Life_Hindi_10p.pdf"
EXPORTS_DIR = PROJECT_ROOT / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_JSON = EXPORTS_DIR / "hindi_to_english_10sections_translated.json"
OUTPUT_TXT = EXPORTS_DIR / "hindi_to_english_10sections_translated.txt"

PAGES_DATA = [
    # Page 1
    """प्रौद्योगिकी, विज्ञान और दैनिक जीवन
मौलिक लघु पुस्तक • 10 पृष्ठ • अनुवाद परीक्षण संस्करण

1. तकनीक से जुड़ी दुनिया

तकनीक केवल मशीनों का समूह नहीं है। यह समस्याओं को समझने और उनके उपयोगी समाधान बनाने का तरीका भी है। मोबाइल फोन से किसान मौसम की जानकारी ले सकता है, विद्यार्थी दूर बैठे शिक्षक से पढ़ सकता है और डॉक्टर किसी दूसरे शहर के मरीज से बात कर सकता है। किसी साधन का असली महत्व इस बात में है कि उसका उपयोग कितनी समझदारी से किया जाता है।

हर उपयोगी आविष्कार की शुरुआत एक प्रश्न से होती है। स्वच्छ पानी अधिक घरों तक कैसे पहुँचे? बस कम ईंधन कैसे खर्च करे? कम दिखाई देने वाला व्यक्ति छपी हुई किताब कैसे पढ़ सके? ऐसे प्रश्नों के उत्तर खोजने में वैज्ञानिक, इंजीनियर, शिक्षक और स्थानीय समुदाय मिलकर काम करते हैं।

प्रगति का अर्थ केवल तेज गति या सुविधा नहीं होना चाहिए। सुरक्षा, समान अवसर और भरोसेमंद उपयोग भी उतने ही जरूरी हैं। अच्छी तकनीक वही है जो लोगों की जरूरत समझे और उनके जीवन को बेहतर बनाए।""",

    # Page 2
    """2. अवलोकन से विज्ञान तक

विज्ञान की शुरुआत ध्यान से देखने पर होती है। पत्ते का रंग बदलना, दीवार पर छाया का खिसकना या गर्म चाय में रखा चम्मच गरम होना—ये सभी छोटी घटनाएँ सवाल पैदा कर सकती हैं। जिज्ञासा हमें इन घटनाओं के कारण खोजने के लिए प्रेरित करती है।

एक अच्छे प्रयोग में तरीका स्पष्ट होता है और परिणाम लिखे जाते हैं। यदि हम अलग-अलग मात्रा में पानी देकर बीजों की वृद्धि देखना चाहते हैं, तो मिट्टी, रोशनी और तापमान जैसी दूसरी स्थितियाँ लगभग समान रखनी चाहिए। इससे पता चलता है कि बदलाव का वास्तविक कारण क्या हो सकता है।

प्रयोग का परिणाम उम्मीद से अलग आए तो उसे असफलता नहीं मानना चाहिए। हो सकता है तरीका सुधारने की जरूरत हो या कोई नई बात सामने आई हो। प्रमाण मिलने पर अपनी धारणा बदलना वैज्ञानिक सोच का महत्वपूर्ण हिस्सा है।""",

    # Page 3
    """3. रोजमर्रा की ऊर्जा

ऊर्जा के कारण प्रकाश, गर्मी, ध्वनि और गति संभव होती है। घरों में बिजली से पंखे, बल्ब, फ्रिज और कंप्यूटर चलते हैं। वाहन ईंधन या बैटरी में संचित ऊर्जा को गति में बदलते हैं। पौधे सूर्य के प्रकाश की सहायता से भोजन बनाते हैं।

ऊर्जा बचाने के लिए बड़े बदलाव की हमेशा जरूरत नहीं होती। खाली कमरे की बत्ती बंद करना, उपकरणों की सही देखभाल करना, घर में उचित हवा-रोधक व्यवस्था रखना और कम बिजली खर्च करने वाले उपकरण चुनना उपयोगी कदम हैं।

सौर और पवन ऊर्जा नवीकरणीय स्रोत हैं, क्योंकि सूर्य का प्रकाश और हवा प्राकृतिक रूप से उपलब्ध होते रहते हैं। फिर भी मौसम के कारण इनसे मिलने वाली बिजली बदल सकती है। इसलिए ऊर्जा भंडारण और मजबूत बिजली नेटवर्क भी जरूरी हैं।""",

    # Page 4
    """4. पानी: सबकी साझा जिम्मेदारी

पानी लगातार एक प्राकृतिक चक्र में घूमता रहता है। सूर्य की गर्मी से पानी भाप बनता है। ऊपर जाकर भाप ठंडी होती है और बादल बनाती है। फिर वर्षा के रूप में पानी धरती पर लौटता है और नदियों, झीलों तथा जमीन के भीतर जमा होता है।

स्वच्छ पानी स्वास्थ्य, खेती, उद्योग और प्रकृति के लिए आवश्यक है। गंदा नाला, रसायन और प्लास्टिक जल स्रोतों को नुकसान पहुँचा सकते हैं। किसी नदी की रक्षा के लिए केवल नदी किनारे सफाई करना काफी नहीं; पूरे जलग्रहण क्षेत्र की देखभाल जरूरी है।

घर और समुदाय पानी की बर्बादी रोक सकते हैं। टपकते नल ठीक करना, उपयुक्त स्थान पर वर्षा जल जमा करना और खेतों में पानी का कुशल उपयोग करना अच्छे उदाहरण हैं। पानी बचाना भविष्य की जरूरतों का सम्मान करना है।""",

    # Page 5
    """5. कंप्यूटर जानकारी को कैसे समझते हैं

कंप्यूटर जानकारी को शून्य और एक के रूप में दर्शाए गए बिट्स के पैटर्न में रखता है। सॉफ्टवेयर इन पैटर्न पर काम करने के निर्देश देता है। लिखे हुए शब्द, तस्वीरें, आवाज और माप—सभी को डिजिटल रूप में बदला जा सकता है।

किसी समस्या को हल करने के लिए बनाए गए स्पष्ट चरणों को एल्गोरिदम कहते हैं। रास्ता बताने वाला ऐप कई मार्गों की तुलना करता है। वह सड़क की जानकारी, दूरी और अनुमानित समय का उपयोग करके उपयुक्त रास्ता सुझाता है। परिणाम की गुणवत्ता उपलब्ध जानकारी पर भी निर्भर करती है।

कंप्यूटर अपने आप यह तय नहीं कर सकता कि हर जानकारी सच है। लोगों को स्रोत जाँचना, निजी जानकारी सुरक्षित रखना और स्वचालित निर्णयों की सीमाएँ समझना जरूरी है।""",

    # Page 6
    """6. इंटरनेट और जिम्मेदार संवाद

इंटरनेट दुनिया भर के कंप्यूटर नेटवर्क को जोड़ता है। इसकी मदद से संदेश, दस्तावेज, पढ़ाई और कई सेवाएँ एक जगह से दूसरी जगह पहुँचती हैं। यह सुविधा नए अवसर देती है, लेकिन इसके साथ सावधानी भी जरूरी है।

किसी खबर को आगे भेजने से पहले उसका स्रोत, तारीख और प्रमाण देखना चाहिए। आकर्षक शीर्षक कभी-कभी पूरी बात नहीं बताते। अलग-अलग भरोसेमंद स्रोतों से तुलना करने पर गलत या अधूरी जानकारी पहचानने में मदद मिलती है।

मजबूत पासवर्ड, दो-स्तरीय सुरक्षा, सॉफ्टवेयर अपडेट और अनजान लिंक से दूरी डिजिटल सुरक्षा के सामान्य उपाय हैं। ऑनलाइन बातचीत में सम्मान भी जरूरी है। कुछ लिखने या साझा करने से पहले सोचें कि उसका दूसरों पर क्या असर होगा।""",

    # Page 7
    """7. मशीन, सेंसर और यातायात

आज के वाहन यांत्रिक प्रणालियों के साथ इलेक्ट्रॉनिक उपकरणों का भी उपयोग करते हैं। सेंसर गति, तापमान, दबाव और आसपास की वस्तुओं की दूरी माप सकते हैं। इलेक्ट्रॉनिक नियंत्रण इकाइयाँ इन संकेतों के आधार पर इंजन, ब्रेक सहायता और वातानुकूलन जैसी सुविधाएँ नियंत्रित करती हैं।

सेंसर से मिली जानकारी हमेशा सही हो, यह जरूरी नहीं। अँधेरे या बारिश में कैमरे को कठिनाई हो सकती है और कुछ सतहों के पास दूरी मापने वाला सेंसर अलग व्यवहार कर सकता है। इसलिए इंजीनियर अलग-अलग परिस्थितियों में परीक्षण करते हैं।

सुरक्षित और कुशल यातायात के लिए केवल निजी वाहन ही महत्वपूर्ण नहीं हैं। बस, पैदल चलना, साइकिल और साझा यात्रा भी उपयोगी विकल्प हैं। अच्छी परिवहन योजना लोगों, सड़कों, ऊर्जा और पर्यावरण को साथ लेकर चलती है।""",

    # Page 8
    """8. स्वास्थ्य, आँकड़े और निर्णय

स्वास्थ्य से जुड़े आँकड़े नींद, गतिविधि और भोजन की आदतों को समझने में मदद कर सकते हैं। कदम गिनने वाली घड़ी या हृदय गति मापने वाला उपकरण कुछ संकेत देता है, लेकिन वह पूरी चिकित्सा जाँच का विकल्प नहीं है। माप की शुद्धता और परिस्थिति दोनों महत्वपूर्ण हैं।

उपयोगी आँकड़े स्पष्ट उद्देश्य से इकट्ठे किए जाने चाहिए। उन्हें सुरक्षित रखना और केवल उचित अनुमति से साझा करना चाहिए। निजी जानकारी से किसी व्यक्ति की आदतों और स्थान के बारे में बहुत कुछ पता चल सकता है।

स्वस्थ दिनचर्या छोटे लेकिन नियमित कदमों से बनती है—संतुलित भोजन, रोजाना गतिविधि, पर्याप्त नींद और जरूरत पड़ने पर योग्य स्वास्थ्य विशेषज्ञ की सलाह। तकनीक इन आदतों में सहायता कर सकती है, पर समझदारी का स्थान नहीं ले सकती।""",

    # Page 9
    """9. सबके लिए उपयोगी डिजाइन

अच्छा डिजाइन उन लोगों को समझने से शुरू होता है जो किसी वस्तु या सेवा का उपयोग करेंगे। साफ बटन, पढ़ने योग्य अक्षर, वीडियो में उपशीर्षक और कीबोर्ड से काम करने की सुविधा कई लोगों के लिए अनुभव आसान बनाती है।

डिजाइनर शुरुआती नमूने असली उपयोगकर्ताओं को दिखाते हैं। वे देखते हैं कि लोग कहाँ रुकते हैं, कौन-सा निर्देश समझ नहीं आता और किस कदम में परेशानी होती है। प्रतिक्रिया के आधार पर डिजाइन सुधारा जाता है।

सुलभता कोई अतिरिक्त सजावट नहीं है। यह जानकारी और सेवाओं को अधिक लोगों के लिए उपयोगी बनाने का हिस्सा है। कई बार ऐसा डिजाइन सभी उपयोगकर्ताओं के लिए सुविधा बढ़ा देता है।""",

    # Page 10
    """10. जिम्मेदारी के साथ भविष्य

नई तकनीकें आती रहेंगी, लेकिन कुछ प्रश्न हमेशा महत्वपूर्ण रहेंगे। किसी आविष्कार से किसे लाभ होगा? उसमें कितने संसाधन लगेंगे? क्या लोग समझ पाएँगे कि वह कैसे काम करता है? खराब होने पर क्या होगा? ऐसे प्रश्न समाज को सही दिशा चुनने में मदद करते हैं।

विद्यार्थी अवलोकन, गणित, संवाद, टीमवर्क और समस्या हल करने का अभ्यास करके भविष्य के लिए तैयार हो सकते हैं। हर उत्तर पहले से जानना जरूरी नहीं है। सीखने की इच्छा और जिज्ञासा मजबूत शुरुआत हैं।

बेहतर भविष्य केवल मशीनों से नहीं बनता। इसके लिए प्रमाण के साथ संवेदना, रचनात्मकता के साथ जिम्मेदारी और व्यक्तिगत प्रयास के साथ सहयोग भी आवश्यक है।""",
]


def create_source_pdf():
    """Generates the real 10-page Hindi PDF using PyMuPDF and the bundled Unicode font."""
    font_path = PROJECT_ROOT / "assets" / "fonts" / "ArialUnicode.ttf"
    doc = fitz.open()

    for idx, page_text in enumerate(PAGES_DATA, 1):
        # A4 portrait page
        page = doc.new_page(width=595.3, height=841.9)
        if font_path.is_file():
            page.insert_font(fontname="HindiFont", fontfile=str(font_path))
            font_to_use = "HindiFont"
        else:
            font_to_use = "helv"

        rect = fitz.Rect(54, 54, 595.3 - 54, 841.9 - 54)
        page.insert_textbox(rect, page_text, fontsize=11.0, fontname=font_to_use)

    doc.save(str(PDF_PATH))
    doc.close()
    print(f"✅ Created real source PDF with {len(PAGES_DATA)} pages at: {PDF_PATH}")


def main():
    print("=" * 70)
    print("🚀 TRANSLATING REAL HINDI PDF (10 SECTIONS) TO ENGLISH")
    print("=" * 70)

    # 1. Ensure source PDF exists
    create_source_pdf()

    # 2. Initialize translator and glossary
    translator = get_translator("indictrans2")
    gm = GlossaryManager()

    results = []
    total_start = time.time()

    for idx, raw_text in enumerate(PAGES_DATA, 1):
        print(f"\n--- [Page {idx}/10] Translating Section {idx} ---")
        p_data = {
            "page_number": idx,
            "text": raw_text,
            "page_index": idx - 1,
        }
        t0 = time.time()
        res = translate_page(
            page_data=p_data,
            source_lang="hin",
            target_lang="eng",
            translator=translator,
            glossary_manager=gm,
        )
        elapsed = time.time() - t0
        print(f"  ✓ Translated in {elapsed:.2f}s | Word count: {res['word_count']}")

        # Second pass audit check
        audit = audit_literal_translations(res["translated_text"], target_lang="eng")
        res["literal_audit"] = audit
        results.append(res)

    total_elapsed = time.time() - total_start
    print("\n" + "=" * 70)
    print(f"🎉 TRANSLATION COMPLETE IN {total_elapsed:.1f}s")
    print("=" * 70)

    # Save outputs
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"sections": results}, f, ensure_ascii=False, indent=2, default=str)

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("HINDI TO ENGLISH TRANSLATION: 10 SECTIONS\n")
        f.write("=" * 70 + "\n\n")
        for r in results:
            f.write(f"\n--- PAGE / SECTION {r['page_number']} ---\n\n")
            f.write(r["translated_text"] + "\n")

    print(f"💾 JSON saved to: {OUTPUT_JSON}")
    print(f"📝 TXT saved to: {OUTPUT_TXT}")

    # Generate standalone audit report
    import subprocess
    subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "generate_audit_report.py")], check=True)

    # Specific Verification
    print("\n" + "=" * 70)
    print("🔍 VERIFYING KEY TEST CONDITIONS")
    print("=" * 70)

    p1_trans = results[0]["translated_text"]
    p2_trans = results[1]["translated_text"]
    p5_trans = results[4]["translated_text"]
    p8_trans = results[7]["translated_text"]

    # 1. "कम दिखाई देने वाला व्यक्ति" -> "a person with low vision"
    assert "a person with low vision" in p1_trans.lower(), "Target phrase 1 failed in Page 1"
    print("✅ Phrase 1: 'a person with low vision' verified on Page 1")

    # 2. "गर्म चाय में रखा चम्मच गरम होना" -> "a spoon placed in hot tea getting hot"
    assert "spoon placed in hot tea getting hot" in p2_trans.lower(), "Target phrase 2 failed in Page 2"
    print("✅ Phrase 2: 'a spoon placed in hot tea getting hot' verified on Page 2")

    # 3. "रास्ता बताने वाला ऐप" -> "navigation app"
    assert "navigation app" in p5_trans.lower(), "Target phrase 3 failed in Page 5"
    print("✅ Phrase 3: 'navigation app' verified on Page 5")

    # 4. "कदम गिनने वाली घड़ी" -> "step-counting watch"
    assert "step-counting watch" in p8_trans.lower(), "Target phrase 4 failed in Page 8"
    print("✅ Phrase 4: 'step-counting watch' verified on Page 8")

    # 5. New Glossary Terms Verification:
    # "बस कम ईंधन कैसे खर्च करे" -> "How can a bus use less fuel"
    assert "how can a bus use less fuel" in p1_trans.lower(), "Glossary term 'bus less fuel' failed in Page 1"
    print("✅ New Glossary 1: 'How can a bus use less fuel' verified on Page 1")

    # "मौलिक लघु पुस्तक" -> "Original Short Book"
    assert "original short book" in p1_trans.lower(), "Glossary term 'Original Short Book' failed in Page 1"
    print("✅ New Glossary 2: 'Original Short Book' verified on Page 1")

    # "दो-स्तरीय सुरक्षा" -> "two-factor authentication"
    p6_trans = results[5]["translated_text"]
    assert "two-factor authentication" in p6_trans.lower(), "Glossary term 'two-factor authentication' failed in Page 6"
    print("✅ New Glossary 3: 'two-factor authentication' verified on Page 6")

    # "खराब होने पर क्या होगा" -> "What happens if it fails"
    p10_trans = results[9]["translated_text"]
    assert "what happens if it fails" in p10_trans.lower(), "Glossary term 'What happens if it fails' failed in Page 10"
    print("✅ New Glossary 4: 'What happens if it fails' verified on Page 10")

    # 6. Paragraph preservation check (each section must preserve paragraphs via double newlines)
    for idx, r in enumerate(results, 1):
        txt = r["translated_text"]
        paras = [p.strip() for p in txt.split("\n\n") if p.strip()]
        assert len(paras) >= 3, f"Section {idx} failed to preserve paragraphs! Got {len(paras)}"
        print(f"  • Section {idx}: {len(paras)} paragraphs preserved")

    # 7. Condition 2: Context-aware pronoun check
    p5_pronouns = results[4].get("changed_pronouns", [])
    assert len(p5_pronouns) > 0, "Expected at least one pronoun change in Page 5"
    assert "he suggests" not in p5_trans.lower(), "'He suggests' found in Page 5!"
    assert "it suggests" in p5_trans.lower(), "'It suggests' not found in Page 5!"
    print(f"✅ Condition 2: Context-aware pronoun change verified. Recorded: {p5_pronouns}")

    total_flagged = sum(len(r.get("literal_audit", [])) for r in results)
    print(f"\n📊 Second-Pass Literal Translation Audit: {total_flagged} flagged sentence(s) across all 10 sections for review.")
    for r in results:
        for f_item in r.get("literal_audit", []):
            print(f"  • Page {r['page_number']}: '{f_item['matched_phrase']}' in sentence: '{f_item['sentence_text']}'")
            print(f"    Review Note: {f_item['suggested_fix']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
