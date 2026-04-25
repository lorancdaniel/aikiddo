# Plan Wdrożenia AI Kids Music Studio

> **Dla agentów wykonawczych:** WYMAGANA PODUMIEJĘTNOŚĆ: użyj `superpowers:subagent-driven-development` albo `superpowers:executing-plans`, jeśli ten plan będzie później wykonywany zadanie po zadaniu.

**Cel:** Zbudować lokalne studio produkcyjne AI do tworzenia wysokiej jakości polskich piosenek dla dzieci, animowanych teledysków oraz 3-5 krótkich rolek z każdego pełnego odcinka.

**Architektura:** Aplikacja działa jako pipeline produkcyjny z osobnymi etapami dla briefu, tekstu piosenki, muzyki, storyboardu, spójnych postaci, scen video, montażu, rolek oraz kontroli jakości. Panel aplikacji działa na laptopie operatora, ale ciężkie generowanie AI odbywa się na osobnym serwerze GPU budowanym od podstaw. Dostęp do serwera odbywa się przez SSH i Tailscale.

**Ważne założenie dotyczące postaci:** Postacie nie są generowane przez API aplikacji. Bazowe postacie, arkusze referencyjne i warianty ekspresji mają być generowane z poziomu Codexa przy użyciu `gpt-image-2`, a następnie zapisywane jako zatwierdzone lokalne referencje projektu. Aplikacja używa tych zapisanych referencji do utrzymania spójności w dalszym pipeline.

**Stack technologiczny:** Python, FastAPI, PostgreSQL, Redis/RQ lub Celery, Tailscale, SSH, rsync albo SFTP, lokalny runtime LLM na serwerze GPU, ComfyUI albo podobny runner workflow dla obrazów i video, FFmpeg, lokalne narzędzia audio/muzyczne, UI w Next.js albo Vue uruchamiane na laptopie.

---

## Pozycjonowanie Produktu

To nie ma być fabryka automatycznych filmów na YouTube. Bezpieczniejszy i bardziej długoterminowy kierunek to małe studio produkcyjne wspierane AI: mniej materiałów, ale każdy z jasnym pomysłem, spójnymi postaciami, dobrą piosenką, sensowną historią i kontrolą jakości.

Pierwszy rynek: polskie piosenki dla dzieci z animowanymi, bajkowymi klipami. Treści mają być atrakcyjne wizualnie, ale nie projektowane jako agresywnie przebodźcowujące. Zamiast "dopaminowych sztuczek" aplikacja ma optymalizować: rytm, refren, czytelność historii, humor, powtarzalność muzyczną, edukacyjny sens i zaufanie rodziców.

## Topologia Systemu: Laptop + Serwer GPU

System jest podzielony na dwie maszyny:

### Laptop Operatora

Rola:

- uruchamia panel aplikacji;
- przechowuje lekki stan projektu albo kopię roboczą;
- służy do pracy w Codexie;
- generuje i zatwierdza postacie przez Codex + `gpt-image-2`;
- wysyła zadania generacyjne na serwer GPU;
- pobiera podglądy, raporty i finalne artefakty;
- umożliwia ręczną akceptację briefu, tekstu, postaci, audio, scen, pełnego filmu i rolek.

Na laptopie nie uruchamiamy ciężkich modeli video/audio, chyba że jako awaryjny fallback.

### Serwer GPU

Rola:

- wykonuje ciężką inferencję lokalnych modeli;
- uruchamia ComfyUI, Wan/LTX/Hunyuan workflow, audio workers, FFmpeg i lokalne LLM;
- przechowuje cache modeli;
- przechowuje robocze artefakty scen i renderów;
- obsługuje kolejkę zadań z laptopa;
- odsyła status, logi i wyniki do panelu aplikacji.

Dostęp:

- SSH tylko po kluczach;
- Tailscale jako prywatna sieć między laptopem i serwerem;
- brak publicznego panelu ComfyUI/API wystawionego do internetu;
- opcjonalnie Tailscale ACL ograniczający dostęp tylko do laptopa operatora.

Rekomendowany przepływ:

1. Laptop tworzy projekt i zapisuje brief.
2. Laptop wysyła zadanie do kolejki.
3. Serwer GPU pobiera zadanie i lokalne assety.
4. Serwer generuje artefakty.
5. Serwer zapisuje wyniki w katalogu projektu.
6. Laptop pobiera tylko potrzebne podglądy albo finalne pliki.
7. Człowiek zatwierdza wynik w panelu.

## Serwer GPU Budowany Od Podstaw

Serwer powinien być projektowany pod długie, stabilne obciążenie GPU, nie pod krótkie benchmarki. Docelowy baseline sprzętowy dla tego projektu to posiadane już: RTX 5090 + 64 GB DDR5 RAM.

Wymagania praktyczne:

- RTX 5090 jako główne GPU generacyjne;
- 64 GB DDR5 RAM jako docelowy RAM serwera;
- szybki NVMe na system i modele;
- osobny duży NVMe/SSD na artefakty projektów;
- mocny zasilacz z zapasem dla GPU i długiego obciążenia;
- bardzo dobre chłodzenie obudowy;
- Linux jako system serwera;
- zdalna administracja przez SSH;
- Tailscale uruchamiany jako usługa systemowa;
- monitoring temperatur, VRAM, użycia dysku i statusu workerów.

Zasada projektowa dla 64 GB RAM:

- pipeline wykonuje ciężkie etapy sekwencyjnie;
- tylko jeden ciężki job GPU naraz: video, image batch, audio generation albo duży LLM;
- lekkie etapy mogą działać równolegle tylko wtedy, gdy nie konkurują o VRAM;
- modele są ładowane i zwalniane per etap, jeśli workflow tego wymaga;
- offload CPU/RAM jest dozwolony, ale nie może prowadzić do swapowania systemu;
- aplikacja ma pokazywać kolejkę, aktualny etap, użycie VRAM/RAM i przewidywany czas końca;
- workflow ma preferować modele i ustawienia mieszczące się stabilnie w 32 GB VRAM i 64 GB RAM.

Katalogi serwera:

```text
/srv/ai-kids-studio/
  app/
  models/
    llm/
    image/
    video/
    audio/
  projects/
  cache/
  logs/
  workers/
```

Zasady:

- modele trzymamy na serwerze, nie synchronizujemy ich na laptop;
- artefakty projektów mają wersje i nie są nadpisywane bez śladu;
- finalne rendery i zatwierdzone referencje postaci są synchronizowane na laptop;
- nieudane generacje zostają w `failed/` do analizy;
- serwer nie publikuje niczego samodzielnie na YouTube.

## Pipeline Jako Podstawowy Mechanizm Pracy

Cała produkcja ma odbywać się przez pipeline. Nie uruchamiamy ręcznych, oderwanych od projektu generacji poza systemem, z wyjątkiem generowania bazowych postaci przez Codex + `gpt-image-2`.

Każdy etap pipeline ma:

- wejściowy manifest;
- wyjściowy manifest;
- status;
- logi;
- wersję użytego modelu;
- parametry generacji;
- linki do artefaktów;
- informację, czy wymaga akceptacji człowieka.

Typowy porządek jobów:

1. `brief.generate`
2. `lyrics.generate`
3. `characters.import_or_approve`
4. `audio.generate_or_import`
5. `storyboard.generate`
6. `keyframes.generate`
7. `keyframes.review`
8. `video.scenes.generate`
9. `video.scenes.review`
10. `render.full_episode`
11. `render.reels`
12. `quality.compliance_report`
13. `publish.prepare_package`

Scheduler:

- utrzymuje kolejkę FIFO z priorytetami;
- blokuje ciężkie joby równoległe;
- pozwala wznowić projekt po restarcie laptopa albo serwera;
- zapisuje checkpoint po każdym ukończonym etapie;
- umożliwia regenerację pojedynczej sceny bez kasowania całego projektu;
- nie przechodzi dalej, jeśli etap wymagający akceptacji nie został zatwierdzony.

## Ograniczenia Platformowe I Prawne

Zasady YouTube trzeba traktować jak wymagania produktu:

- Piosenki, bajkowe postacie, animacje i historie dla dzieci najczęściej będą kwalifikować się jako "made for kids".
- Treści "made for kids" mają ograniczone funkcje, między innymi brak komentarzy, powiadomień i reklam personalizowanych.
- YouTube może ograniczyć albo wyłączyć monetyzację kanału, jeśli uzna treści za masowo produkowane, powtarzalne lub niskiej jakości.
- Treści dla dzieci powinny być odpowiednie wiekowo, wzbogacające, angażujące, inspirujące i łatwe do zrozumienia.
- Każdy pełny odcinek i każda rolka muszą przechodzić kontrolę bezpieczeństwa i jakości.

Źródła do regularnego sprawdzania:

- https://support.google.com/youtubecreatorstudio/answer/1311392
- https://support.google.com/youtube/answer/10774223
- https://support.google.com/youtube/answer/9632097
- https://support.google.com/youtube/answer/9528076
- https://support.google.com/youtube/answer/14328491

## Kluczowa Zasada: Spójność Postaci

Postacie są najważniejszym aktywem marki. Nie mogą wyglądać inaczej w każdej scenie.

Wymagania:

- Każda postać ma stały identyfikator, na przykład `toothbrush_friend_v1`.
- Każda postać ma własny plik `character_bible.json`.
- Każda postać ma zatwierdzony arkusz referencyjny wygenerowany przez `gpt-image-2` z poziomu Codexa.
- Arkusz referencyjny powinien zawierać: widok z przodu, profil, tył, 4-6 emocji, pozy akcji, paletę kolorów, ubrania/rekwizyty i zakazane warianty.
- Po zatwierdzeniu postaci nie wolno zmieniać jej wyglądu w ramach tej samej wersji.
- Jeśli postać musi się zmienić, powstaje nowa wersja, na przykład `character_v2`, a stare projekty nadal używają poprzednich referencji.
- Żaden etap generowania scen nie powinien startować bez zatwierdzonych referencji postaci.

## Wyjątek Od Lokalności: gpt-image-2 W Codexie

Pierwotne założenie generowania to praca na własnym serwerze GPU z RTX 5090 i lokalnymi modelami. Dla postaci wprowadzamy kontrolowany wyjątek:

- bazowe postacie i arkusze referencyjne są generowane przez Codex z użyciem `gpt-image-2`;
- aplikacja nie wywołuje OpenAI API do generowania postaci;
- wygenerowane obrazy są zapisywane lokalnie jako zatwierdzone aktywa;
- dalsze etapy pipeline pracują na lokalnych referencjach;
- każda wygenerowana referencja musi być ręcznie zaakceptowana przed użyciem.

Uzasadnienie: postacie są krytyczne dla jakości i marki. Lepiej wygenerować mniej, ale bardzo dobre i spójne referencje, niż próbować tworzyć postacie od zera przy każdej scenie lokalnym modelem video.

## Główny Pipeline Produkcyjny

### Etap 1: Brief Projektu

Wejście:

- temat, na przykład mycie zębów, emocje, kolory, liczenie, sprzątanie zabawek;
- grupa wiekowa, na przykład 3-5 albo 5-7;
- docelowa emocja: radość, ciekawość, spokój, odwaga;
- wartość edukacyjna albo emocjonalna;
- wybrane postacie z biblioteki.

Wyjście:

- `brief.json`
- roboczy tytuł;
- grupa docelowa;
- morał albo cel edukacyjny;
- dozwolone motywy wizualne;
- zakazane motywy;
- kierunek muzyczny;
- szkic historii.

Bramka jakości:

- Człowiek zatwierdza brief w MVP.

### Etap 2: Tekst Piosenki

Wejście:

- zatwierdzony brief;
- struktura piosenki;
- wybrany styl muzyczny.

Wyjście:

- `lyrics.json`
- zwrotki;
- refren;
- opcjonalny bridge;
- notatki rytmiczne;
- ocena języka dla wieku;
- notatki bezpieczeństwa.

Reguły:

- Prosty, naturalny język polski.
- Jasny i łatwy do zapamiętania refren.
- Brak przemocy, seksualizacji, straszenia, manipulacji i zachęt do niebezpiecznych zachowań.
- Brak fałszywych obietnic edukacyjnych.
- Brak upychania słów kluczowych.
- Brak zachęt typu "oglądaj dalej bez końca".

Bramka jakości:

- Człowiek zatwierdza tekst w MVP.

### Etap 3: Muzyka I Wokal

Wejście:

- zatwierdzony tekst;
- kierunek muzyczny;
- tempo;
- docelowa emocja.

Wyjście:

- `instrumental.wav`
- `vocals.wav`
- `song.wav`
- `timestamps.json`
- opcjonalnie katalog `stems/`

Wymagania:

- Naturalna polska wymowa.
- Przyjemna barwa, bez agresywnego masteringu.
- Stały głos narratora albo postaci.
- Czysty miks.
- Znaczniki czasu dla słów, refrenów i beatów.

Ryzyko:

- Lokalny, wysokiej jakości śpiew po polsku będzie jednym z najtrudniejszych elementów.

Bramka jakości:

- Człowiek zatwierdza audio w MVP.

### Etap 4: Storyboard

Wejście:

- finalne audio;
- tekst z timestampami;
- zatwierdzone postacie;
- styl wizualny.

Wyjście:

- `storyboard.json`
- lista scen;
- czas trwania ujęć;
- akcja w każdej scenie;
- postacie obecne w scenie;
- prompt wizualny;
- prompt negatywny;
- notatki kamery/ruchu;
- cel narracyjny albo edukacyjny sceny.

Reguły:

- Sceny po około 3-6 sekund.
- Każda scena ma konkretną akcję, nie tylko dekorację.
- Film ma początek, rozwinięcie i zakończenie.
- Tempo jest atrakcyjne, ale nie chaotyczne.
- Storyboard oznacza najlepsze momenty jako kandydatów na rolki.

Bramka jakości:

- Człowiek zatwierdza storyboard w MVP.

### Etap 5: Generowanie I Zatwierdzanie Postaci Przez Codex + gpt-image-2

Wejście:

- opis postaci;
- rola postaci w świecie;
- styl wizualny kanału;
- paleta kolorów;
- ograniczenia wieku i bezpieczeństwa.

Proces:

1. Codex generuje arkusz postaci z użyciem `gpt-image-2`.
2. Operator zapisuje wygenerowane obrazy do katalogu postaci.
3. Aplikacja tworzy lub aktualizuje `character_bible.json`.
4. Człowiek zatwierdza referencje.
5. Pipeline blokuje generowanie scen, jeśli referencje nie są zatwierdzone.

Wyjście:

- `characters/<character_id>/character_bible.json`
- `characters/<character_id>/reference_sheet.png`
- `characters/<character_id>/expressions.png`
- `characters/<character_id>/poses.png`
- `characters/<character_id>/palette.json`
- `characters/<character_id>/do_not_change.md`

Reguły spójności:

- Ten sam kształt głowy/twarzy.
- Te same kolory.
- Te same ubrania albo rekwizyty.
- Ten sam ogólny styl renderowania.
- Bez losowych zmian wieku, płci, proporcji, ubrań lub mimiki.
- Każda scena musi odwoływać się do właściwego `character_id` i wersji.

### Etap 6: Spójność Wizualna

Wejście:

- zatwierdzona biblia postaci;
- zatwierdzone referencje;
- storyboard;
- styl kanału.

Wyjście:

- raport spójności;
- lista scen wymagających regeneracji;
- informacja, które referencje zostały użyte.

Wymagania:

- Postacie w scenach są porównywane z referencją.
- Scena jest odrzucana, jeśli postać wygląda jak inna postać.
- Każda wygenerowana scena zapisuje metadane: prompt, seed, wersję postaci, workflow, datę i status akceptacji.

### Etap 7: Keyframe'y

Wejście:

- storyboard;
- zatwierdzone referencje postaci;
- styl wizualny.

Wyjście:

- `scenes/001/keyframe.png`
- `scenes/001/metadata.json`
- kolejne pliki dla każdej sceny.

Kontrole jakości:

- Brak zniekształconych twarzy i ciał.
- Brak dodatkowych kończyn.
- Brak strasznych artefaktów.
- Brak tematów dorosłych.
- Brak niebezpiecznych przedmiotów.
- Postać jest zgodna z zatwierdzoną referencją.
- Scena odpowiada storyboardowi.

Bramka jakości:

- Człowiek zatwierdza keyframe'y w MVP.

### Etap 8: Generowanie Scen Video

Wejście:

- zatwierdzone keyframe'y;
- prompt ruchu;
- timestampy audio;
- referencje postaci.

Wyjście:

- `scenes/001/video_raw.mp4`
- `scenes/001/video_clean.mp4`
- analogiczne pliki dla kolejnych scen.

Wymagania:

- Generujemy krótkie sceny, nie cały film naraz.
- Ruch wspiera tekst i historię.
- Brak nagłych, niepokojących transformacji.
- Brak nadmiernego migania.
- Brak losowego tekstu wygenerowanego w obrazie.
- Spójność postaci ma pierwszeństwo przed efektownością sceny.

### Etap 9: Montaż Pełnego Odcinka

Wejście:

- czyste sceny video;
- finalne audio;
- timestampy słów i beatów;
- momenty oznaczone jako kandydaci na rolki.

Wyjście:

- `renders/youtube_16x9.mp4`
- `renders/thumbnails/thumb_01.png`
- `renders/thumbnails/thumb_02.png`
- `renders/thumbnails/thumb_03.png`
- `renders/captions.srt`

Wymagania:

- Montaż przez FFmpeg.
- Cięcia dopasowane do muzyki.
- Opcjonalne napisy karaoke.
- Miniatura z zatwierdzonych materiałów, bez clickbaitu.
- Pipeline generuje 2-3 warianty miniatury dla pełnego odcinka.
- Miniatury mają być czytelne na mobile, bez mylących emocji, bez straszenia i bez nadmiaru tekstu.
- Intro/outro tylko jeśli realnie wzmacnia markę.

### Etap 10: Pakiet Rolek Z Każdego Odcinka

Każdy pełny odcinek musi produkować 3-5 krótkich materiałów pionowych.

Wejście:

- finalny pełny odcinek;
- lista scen;
- timestampy słów i beatów;
- zatwierdzone sceny;
- zatwierdzone postacie.

Wyjście:

- `renders/reels/reel_01_9x16.mp4`
- `renders/reels/reel_02_9x16.mp4`
- `renders/reels/reel_03_9x16.mp4`
- opcjonalnie `renders/reels/reel_04_9x16.mp4`
- opcjonalnie `renders/reels/reel_05_9x16.mp4`
- `renders/reels/thumbnails/reel_01_thumb.png`
- `renders/reels/thumbnails/reel_02_thumb.png`
- `renders/reels/thumbnails/reel_03_thumb.png`
- `renders/reels/reels_metadata.json`

Rodzaje rolek:

- rolka refrenowa: najbardziej chwytliwy fragment;
- rolka postaci: zabawny albo emocjonalny moment postaci;
- rolka edukacyjna: morał lub konkretna umiejętność;
- rolka wizualna: najlepiej wyglądająca sekwencja;
- rolka call-and-response: fragment, który dziecko może powtórzyć.

Reguły:

- Każda rolka działa samodzielnie bez pełnego odcinka.
- Każda rolka ma własny hook, tytuł, opis, hashtagi i miniaturę.
- Każda rolka przechodzi tę samą kontrolę jakości i bezpieczeństwa.
- Nie robimy pięciu rolek na siłę. Jeśli są tylko trzy mocne fragmenty, eksportujemy trzy.
- Rolki nie mogą być mylące, straszące ani nadmiernie stymulujące.
- Rolki muszą używać tych samych spójnych postaci co pełny odcinek.

### Etap 10.1: Paczka Publikacyjna Gotowa Do Wrzucenia

Pipeline ma kończyć się paczką gotową do ręcznego uploadu na YouTube, YouTube Shorts, Instagram Reels i TikTok. Nie chodzi tylko o pliki video, ale o komplet metadanych i assetów.

Wejście:

- zatwierdzony pełny odcinek;
- zatwierdzone rolki;
- zatwierdzone miniatury;
- raport zgodności;
- opis treści i cel edukacyjny.

Wyjście:

```text
final/publish_ready/
  youtube/
    video.mp4
    thumbnail.png
    captions.srt
    title.txt
    description.txt
    hashtags.txt
    upload_settings.json
    disclosure_notes.md
    checklist.md
  shorts/
    short_01/
      video.mp4
      thumbnail.png
      title.txt
      description.txt
      hashtags.txt
      upload_settings.json
      checklist.md
    short_02/
    short_03/
  reels/
    reel_01/
      video.mp4
      thumbnail.png
      caption.txt
      hashtags.txt
      checklist.md
    reel_02/
    reel_03/
```

Wymagane metadane dla pełnego filmu YouTube:

- 3 propozycje tytułu, z jedną rekomendowaną;
- finalny tytuł w `title.txt`;
- opis w `description.txt`;
- hashtagi w `hashtags.txt`;
- informacja o AI/synthetic content, jeśli wymagana;
- sugerowana kategoria;
- ustawienie `made_for_kids`;
- język: polski;
- opcjonalny plik napisów;
- notatka, dlaczego miniatura nie jest myląca;
- checklista przed publikacją.

Wymagane metadane dla Shorts/Reels:

- tytuł albo hook;
- krótki opis/caption;
- hashtagi;
- miniatura;
- informacja, z którego pełnego odcinka pochodzi materiał;
- link/tekst zachęty do obejrzenia pełnego odcinka, bez agresywnego clickbaitu;
- checklista jakości.

Reguły:

- Paczka jest gotowa do publikacji ręcznej, ale aplikacja nie publikuje automatycznie w MVP.
- Wszystkie teksty mają być po polsku w pierwszej wersji.
- Opisy i hashtagi nie mogą obiecywać czegoś, czego nie ma w filmie.
- Hashtagi mają być ograniczone i trafne, bez keyword stuffingu.
- Miniatury i tytuły muszą być zgodne z treścią i zasadami kids-content.
- Każda paczka publikacyjna zapisuje dokładną wersję materiałów, które zostały zatwierdzone.

### Etap 11: Kontrola Jakości I Zgodności

Wejście:

- pełny render;
- pakiet rolek;
- miniatura;
- tytuł;
- opis;
- tagi;
- notatki o użyciu AI.
- paczka publikacyjna.

Wyjście:

- `compliance_report.json`
- notatki zgodności dla każdej rolki;
- decyzja pass/fail;
- lista problemów;
- checklista publikacji;
- status `publish_ready` albo `blocked`.

Kontrole:

- Prawdopodobna klasyfikacja "made for kids".
- Brak mylącego tytułu i miniatury.
- Opis, hashtagi i tytuły są zgodne z realną treścią.
- Ustawienia publikacji są jawne i poprawne dla kids-content.
- Brak niskiej jakości autogeneracji.
- Brak niebezpiecznych treści dla dzieci.
- Brak dorosłych tematów w animacji wyglądającej na rodzinną.
- Brak cudzych postaci, marek, melodii lub oczywistych imitacji.
- Brak masowej powtarzalności między odcinkami.
- Jasna wartość edukacyjna, emocjonalna albo wyobrażeniowa.
- Każda rolka jest prawdziwa, odpowiednia wiekowo i reprezentuje pełny odcinek.
- Paczka publikacyjna zawiera wszystkie pliki wymagane do ręcznego uploadu.

Bramka jakości:

- Człowiek zatwierdza pełny odcinek i każdą rolkę przed publikacją.

## Proponowana Struktura Katalogów

```text
ai-kids-music-studio/
  README.md
  docs/
    superpowers/
      plans/
        2026-04-25-ai-kids-music-studio.md
    architecture/
    research/
  app/
    api/
    remote/
      ssh_client/
      tailscale/
      artifact_sync/
    workers/
    pipelines/
    validators/
    render/
    storage/
    models/
    ui/
  projects/
    <project-id>/
      brief.json
      lyrics.json
      song.wav
      timestamps.json
      storyboard.json
      characters/
        <character_id>/
          character_bible.json
          reference_sheet.png
          expressions.png
          poses.png
          palette.json
          do_not_change.md
      scenes/
      renders/
        thumbnails/
        reels/
          thumbnails/
      final/
        publish_ready/
  research/
    models.md
    youtube-policy-notes.md
    quality-benchmarks.md
  server/
    provisioning/
    services/
    workers/
    monitoring/
```

## Moduły Aplikacji

### 1. Panel Produkcyjny

Odpowiedzialność:

- tworzenie i zarządzanie projektami;
- status pipeline'u;
- podgląd briefu, tekstu, audio, storyboardu, keyframe'ów, scen, pełnego renderu i rolek;
- zatwierdzanie, odrzucanie i ponowne generowanie etapów;
- zarządzanie biblioteką postaci i stylem kanału.

Pierwsza wersja:

- lista projektów;
- szczegóły projektu;
- timeline etapów;
- ręczne zatwierdzenia;
- podgląd artefaktów.

### 2. Orkiestrator Pipeline'u

Odpowiedzialność:

- przechowywanie stanu projektu;
- uruchamianie etapów w kolejności;
- wznawianie nieudanych etapów;
- śledzenie artefaktów;
- blokowanie publikacji bez wymaganych zgód.
- delegowanie ciężkich zadań na serwer GPU przez kolejkę i remote executor.
- planowanie jobów pod ograniczenia RTX 5090 + 64 GB RAM;
- pilnowanie, żeby ciężkie modele nie działały równolegle.

Stany:

- `draft`
- `brief_ready`
- `lyrics_ready`
- `audio_ready`
- `storyboard_ready`
- `characters_ready`
- `keyframes_ready`
- `video_scenes_ready`
- `render_ready`
- `short_form_pack_ready`
- `compliance_passed`
- `approved_for_publish`

### 2.1. Remote Generation Gateway

Odpowiedzialność:

- utrzymywanie połączenia z serwerem GPU przez Tailscale;
- wykonywanie komend zdalnych przez SSH;
- wysyłanie manifestów zadań;
- synchronizacja artefaktów przez rsync/SFTP;
- pobieranie statusu workerów;
- obsługa timeoutów, retry i przerwanych połączeń;
- zapisywanie logów zdalnych przy projekcie.

Wymagania:

- brak haseł w kodzie;
- autoryzacja tylko kluczem SSH;
- jawne mapowanie ścieżek laptop-serwer;
- każde zadanie ma `job_id`, `project_id`, `stage`, `input_manifest`, `output_manifest` i status;
- laptop może wznowić pipeline po restarcie.

### 2.2. GPU Server Agent

Odpowiedzialność:

- działa na serwerze GPU;
- odbiera zadania z kolejki albo katalogu `jobs/incoming`;
- uruchamia odpowiedni worker;
- zapisuje logi i artefakty;
- raportuje status do laptopa;
- nie podejmuje decyzji publikacyjnych.
- wymusza limit jednego ciężkiego joba GPU naraz;
- raportuje użycie VRAM/RAM przed, w trakcie i po jobie.

Pierwsza wersja może być prosta:

- bez publicznego API;
- zadania jako pliki JSON;
- uruchamianie przez SSH;
- status jako plik JSON w katalogu projektu.

### 3. Creative Director Worker

Odpowiedzialność:

- generowanie briefów;
- dbanie o różnorodność odcinków;
- pilnowanie wieku odbiorcy;
- pilnowanie, żeby treść nie była szablonowa.

### 4. Lyrics Worker

Odpowiedzialność:

- generowanie tekstu po polsku;
- sprawdzanie prostoty języka;
- kontrola refrenu, rytmu i bezpieczeństwa.

### 5. Audio Worker

Odpowiedzialność:

- generowanie albo import audio;
- tworzenie stemów i timestampów;
- kontrola głośności, długości i jakości.

### 6. Storyboard Worker

Odpowiedzialność:

- dzielenie piosenki na sceny;
- generowanie promptów wizualnych;
- wskazywanie kandydatów na rolki;
- dbanie o spójną historię.

### 7. Character Reference Worker

Odpowiedzialność:

- zarządzanie referencjami postaci wygenerowanymi przez Codex + `gpt-image-2`;
- tworzenie i walidacja `character_bible.json`;
- pilnowanie wersji postaci;
- blokowanie scen bez zatwierdzonych referencji.

Ważne:

- Ten moduł nie wywołuje OpenAI API.
- Operator/Codex generuje obrazy postaci poza aplikacją.
- Aplikacja przechowuje i egzekwuje zatwierdzone referencje.

### 8. Visual Worker

Odpowiedzialność:

- generowanie keyframe'ów na bazie zatwierdzonych referencji;
- zapisywanie promptów, seedów i metadanych;
- kontrola spójności postaci.

### 9. Video Worker

Odpowiedzialność:

- generowanie krótkich animowanych scen;
- czyszczenie, upscaling i normalizacja scen;
- regeneracja scen z zachowaniem referencji postaci.

### 10. Render Worker

Odpowiedzialność:

- składanie pełnego odcinka;
- dodawanie napisów;
- eksport wariantów platformowych;
- przygotowanie źródeł dla rolek;
- działanie na serwerze GPU albo CPU serwera, nie na laptopie, jeśli render jest ciężki.

### 11. Short-Form Derivative Worker

Odpowiedzialność:

- wybór najlepszych momentów z pełnego odcinka;
- wygenerowanie 3-5 rolek;
- przygotowanie hooków, tytułów i opisów;
- przygotowanie hashtagów i miniaturek dla każdej rolki;
- eksport 9:16;
- odrzucanie słabych, mylących albo niespójnych klipów.

### 12. Publish Package Worker

Odpowiedzialność:

- zbudowanie kompletnej paczki publikacyjnej dla YouTube;
- zbudowanie kompletnej paczki dla każdego Shorta/Reelsa;
- wygenerowanie tytułów, opisów, hashtagów, captions i checklist;
- wybranie rekomendowanej miniatury z zatwierdzonych wariantów;
- zapis ustawień uploadu w `upload_settings.json`;
- sprawdzenie, czy paczka jest kompletna przed statusem `publish_ready`.

Ważne:

- Worker nie publikuje automatycznie w MVP.
- Wynik ma być dosłownie gotowy do ręcznego uploadu.
- Publikacja wymaga ręcznej akceptacji człowieka.

### 13. Quality And Compliance Worker

Odpowiedzialność:

- raport jakości i zgodności;
- sprawdzanie pełnego odcinka i wszystkich rolek;
- blokowanie publikacji przy problemach;
- dokumentowanie, dlaczego materiał został zatwierdzony;
- częściowe działanie na laptopie, ale analiza finalnych plików i ekstrakcja klatek może odbywać się na serwerze.

## Zakres MVP

MVP ma wyprodukować jeden kompletny, wysokiej jakości odcinek oraz minimum trzy rolki, przy czym panel działa na laptopie, a generowanie i renderowanie odbywa się na serwerze GPU.

W MVP jest:

- tworzenie projektu;
- generowanie briefu;
- generowanie tekstu piosenki;
- ręczna akceptacja tekstu;
- import albo wrapper generowania audio;
- generowanie storyboardu;
- generowanie i zapis referencji postaci przez Codex + `gpt-image-2`;
- ręczna akceptacja postaci;
- generowanie keyframe'ów z referencjami;
- ręczna akceptacja keyframe'ów;
- generowanie scen video;
- render pełnego odcinka przez FFmpeg;
- 3-5 rolek 9:16;
- miniatury dla pełnego odcinka;
- miniatury dla rolek;
- tytuły, opisy, hashtagi i ustawienia uploadu;
- kompletna paczka `publish_ready`;
- raport jakości i zgodności;
- połączenie laptop-serwer przez Tailscale i SSH;
- zdalne uruchamianie workerów na serwerze GPU;
- synchronizacja artefaktów między serwerem i laptopem.

Nie ma w MVP:

- automatycznego uploadu na YouTube;
- pełnej obsługi wielu języków;
- automatycznej publikacji bez człowieka;
- zaawansowanych testów A/B;
- masowej produkcji katalogu;
- w pełni automatycznego scoringu ML dla spójności postaci.

## Fazy Wdrożenia

### Faza 0: Budowa I Przygotowanie Serwera GPU

- [ ] Złożyć serwer pod długotrwałe obciążenie RTX 5090 + 64 GB DDR5 RAM.
- [ ] Zainstalować Linux.
- [ ] Zainstalować sterowniki NVIDIA, CUDA i narzędzia monitoringu.
- [ ] Skonfigurować SSH tylko na kluczach.
- [ ] Zainstalować i skonfigurować Tailscale.
- [ ] Utworzyć katalog `/srv/ai-kids-studio/`.
- [ ] Utworzyć katalogi `models/`, `projects/`, `cache/`, `logs/`, `workers/`.
- [ ] Skonfigurować automatyczne uruchamianie workerów po restarcie.
- [ ] Skonfigurować monitoring GPU/RAM/dysku widoczny z panelu aplikacji.
- [ ] Przetestować połączenie laptop-serwer przez Tailscale.
- [ ] Przetestować rsync/SFTP artefaktów między laptopem i serwerem.

### Faza 1: Szkielet Projektu I Storage

- [ ] Utworzyć backend Python.
- [ ] Utworzyć szkielet UI.
- [ ] Ustalić lokalny format przechowywania artefaktów.
- [ ] Ustalić mapowanie ścieżek laptop-serwer.
- [ ] Utworzyć schemat bazy projektów.
- [ ] Utworzyć maszynę stanów pipeline'u.
- [ ] Dodać endpointy create/list/detail dla projektów.
- [ ] Dodać testy cyklu życia projektu.

### Faza 1.1: Remote Execution

- [ ] Dodać konfigurację serwera GPU: host Tailscale, user SSH, ścieżki remote.
- [ ] Zaimplementować `RemoteGenerationGateway`.
- [ ] Dodać format `job_manifest.json`.
- [ ] Dodać zdalne uruchamianie prostego testowego joba przez SSH.
- [ ] Dodać synchronizację input/output przez rsync albo SFTP.
- [ ] Dodać scheduler blokujący równoległe ciężkie joby GPU.
- [ ] Dodać checkpoint po każdym zakończonym etapie pipeline.
- [ ] Dodać podgląd kolejki i aktualnego etapu w UI.
- [ ] Dodać retry i timeouty.
- [ ] Dodać test, że pipeline potrafi wznowić zadanie po przerwanym połączeniu.

### Faza 2: Brief I Tekst

- [ ] Dodać adapter lokalnego LLM.
- [ ] Dodać schemat `brief.json`.
- [ ] Dodać schemat `lyrics.json`.
- [ ] Zaimplementować Creative Director worker.
- [ ] Zaimplementować Lyrics worker.
- [ ] Dodać reguły bezpieczeństwa.
- [ ] Dodać flow akceptacji briefu i tekstu w UI.
- [ ] Dodać testy walidacji schematów i przejść stanów.

### Faza 3: Postacie Przez Codex + gpt-image-2

- [ ] Zdefiniować format `character_bible.json`.
- [ ] Zdefiniować wymagany zestaw referencji postaci.
- [ ] Utworzyć katalog `characters/<character_id>/`.
- [ ] Dodać instrukcję generowania postaci przez Codex z użyciem `gpt-image-2`.
- [ ] Dodać import i rejestrację wygenerowanych referencji.
- [ ] Dodać ręczne zatwierdzanie postaci.
- [ ] Zablokować pipeline scen, jeśli postacie nie są zatwierdzone.
- [ ] Dodać testy wersjonowania postaci.

### Faza 4: Audio

- [ ] Wybrać lokalny sposób generowania albo importu muzyki.
- [ ] Zaimplementować Audio worker.
- [ ] Zapisywać audio i metadane.
- [ ] Dodać walidację długości i głośności.
- [ ] Dodać ręczną akceptację audio.
- [ ] Dodać testy śledzenia artefaktów.

### Faza 5: Storyboard

- [ ] Dodać schemat `storyboard.json`.
- [ ] Zaimplementować Storyboard worker.
- [ ] Generować prompty i prompty negatywne.
- [ ] Oznaczać kandydatów na rolki.
- [ ] Dodać kontrole narracji i długości scen.
- [ ] Dodać UI review storyboardu.
- [ ] Dodać testy poprawnych i błędnych storyboardów.

### Faza 6: Keyframe'y I Spójność Postaci

- [ ] Wybrać workflow runner dla obrazów.
- [ ] Zaimplementować Visual worker.
- [ ] Zapisywać keyframe'y per scena.
- [ ] Do każdego keyframe'a zapisywać wersję postaci.
- [ ] Dodać akceptację/odrzucenie/regenerację keyframe'ów.
- [ ] Dodać podstawową checklistę spójności.
- [ ] Dodać testy blokowania scen przy braku referencji.

### Faza 7: Sceny Video

- [ ] Wybrać workflow runner dla video.
- [ ] Zaimplementować Video worker.
- [ ] Zapisywać raw i clean video per scena.
- [ ] Dodać obsługę błędów i regeneracji.
- [ ] Dodać UI review scen.
- [ ] Dodać testy wersjonowania artefaktów.

### Faza 8: Render Pełnego Odcinka

- [ ] Zaimplementować builder komend FFmpeg.
- [ ] Dodać eksport 16:9.
- [ ] Dodać napisy dla pełnego odcinka.
- [ ] Dodać generowanie 2-3 wariantów miniatury pełnego odcinka.
- [ ] Dodać tracking finalnego renderu.
- [ ] Dodać podgląd renderu w UI.
- [ ] Dodać testy generowania komend renderu.

### Faza 9: Pakiet Rolek

- [ ] Dodać schemat `reels_metadata.json`.
- [ ] Zaimplementować wybór kandydatów na rolki.
- [ ] Generować 3-5 planów rolek z timestampów i scen.
- [ ] Dodać builder crop/reframe 9:16.
- [ ] Renderować `reel_01_9x16.mp4` do `reel_05_9x16.mp4`, jeśli jest wystarczająco dużo mocnych kandydatów.
- [ ] Dodać hook, tytuł i opis dla każdej rolki.
- [ ] Dodać miniaturę i hashtagi dla każdej rolki.
- [ ] Dodać ręczne zatwierdzanie każdej rolki.
- [ ] Dodać test, że projekt nie może być publish-ready bez minimum 3 zatwierdzonych rolek.

### Faza 10: Paczka Publikacyjna

- [ ] Dodać schemat `upload_settings.json`.
- [ ] Dodać schemat `publish_package_manifest.json`.
- [ ] Generować `final/publish_ready/youtube/`.
- [ ] Generować `final/publish_ready/shorts/`.
- [ ] Generować `final/publish_ready/reels/`.
- [ ] Zapisywać `title.txt`, `description.txt`, `hashtags.txt`, `captions.srt`, `thumbnail.png` i `checklist.md`.
- [ ] Dodać UI pokazujące kompletność paczki publikacyjnej.
- [ ] Dodać test, że projekt nie może mieć statusu `publish_ready`, jeśli brakuje video, miniatury, opisu, hashtagów albo checklisty.

### Faza 11: Zgodność I Przygotowanie Publikacji

- [ ] Dodać schemat `compliance_report.json`.
- [ ] Zaimplementować checklistę jakości i zgodności.
- [ ] Wymusić finalną akceptację człowieka.
- [ ] Generować tytuł, opis, tagi, disclosure notes i metadane rolek.
- [ ] Dodać katalog publish-ready.
- [ ] Dodać testy blokowania publikacji bez akceptacji.

## Bramki Jakości

Każdy pełny odcinek musi spełniać:

- temat jest odpowiedni dla dzieci;
- tekst jest naturalny po polsku;
- refren jest łatwy do zapamiętania;
- audio jest przyjemne i czyste;
- film ma początek, rozwinięcie i zakończenie;
- postacie są spójne z zatwierdzonymi referencjami;
- animacje nie zawierają niepokojących artefaktów;
- treść ma wartość edukacyjną, emocjonalną albo wyobrażeniową;
- odcinek różni się znacząco od poprzednich;
- miniatura i tytuł są uczciwe;
- opis i hashtagi są trafne, bez keyword stuffingu;
- pełny odcinek ma kompletną paczkę YouTube gotową do uploadu;
- każdy Short/Reel ma kompletną paczkę gotową do uploadu;
- powstają minimum 3 zatwierdzone rolki;
- każda rolka działa jako samodzielny klip;
- każda rolka używa zatwierdzonych, spójnych postaci;
- raport zgodności jest zatwierdzony przez człowieka.

## Główne Ryzyka

- Lokalny śpiew po polsku może nie osiągnąć jakości produkcyjnej.
- Spójność postaci w animowanych scenach będzie trudna i wymaga rygorystycznych referencji.
- RTX 5090 ma dużą moc, ale 32 GB VRAM nadal ogranicza część dużych modeli video, szczególnie jeśli będą uruchamiane z wysoką rozdzielczością albo bez offloadu.
- Serwer GPU z 64 GB RAM wymaga sekwencyjnego pipeline'u i świadomego zarządzania modelami, żeby nie doprowadzać do swapowania.
- Serwer GPU będzie wymagał stabilnego zasilania, chłodzenia, monitoringu i dużej ilości miejsca na modele oraz artefakty.
- Połączenie laptop-serwer przez Tailscale/SSH musi być odporne na zerwanie, bo generacje video mogą trwać długo.
- Treści "made for kids" mogą mieć niższe przychody z reklam.
- Nadmierna automatyzacja może wyglądać jak masowa, nieautentyczna produkcja.
- Zbyt agresywne rolki mogą pogorszyć zaufanie rodziców i jakość kanału.

## Metryki Sukcesu

Metryki produkcyjne:

- czas od briefu do finalnego renderu;
- czas od finalnego renderu do zatwierdzonego pakietu rolek;
- czas oczekiwania w kolejce serwera GPU;
- czas generowania per scena;
- liczba nieudanych jobów remote;
- średni transfer artefaktów laptop-serwer;
- liczba regeneracji na zaakceptowaną scenę;
- procent scen zaakceptowanych za pierwszym razem;
- czas ręcznej kontroli na odcinek;
- liczba zatwierdzonych rolek na odcinek.

Metryki jakości:

- naturalność tekstu po polsku;
- jakość audio;
- spójność postaci;
- czytelność historii;
- brak przebodźcowania;
- samodzielna zrozumiałość rolek.

Metryki YouTube/social:

- CTR miniatury;
- średni czas oglądania;
- rewatch rate;
- konwersja z rolek do pełnego odcinka;
- subskrypcje z rolek;
- stabilność monetyzacji;
- view-through rate rolek.

## Pierwszy Eksperyment

Pilot:

- temat: "Myjemy ząbki";
- wiek: 3-5;
- postacie: dziecko i przyjazna szczoteczka;
- długość: 90-120 sekund;
- muzyka: prosty, pogodny pop/folk;
- styl: ciepła animacja 2D/3D;
- lekcja: mycie zębów może być fajną częścią spokojnej rutyny;
- pakiet rolek: 3-5 pionowych klipów z refrenu, momentu szczoteczki i morału.

Kryteria akceptacji pilota:

- tekst brzmi naturalnie po polsku;
- refren jest zapamiętywalny;
- postacie są spójne od początku do końca;
- referencje postaci są wygenerowane i zatwierdzone przez Codex + `gpt-image-2`;
- brak niepokojących artefaktów;
- rodzic rozumie wartość odcinka bez czytania opisu;
- minimum 3 rolki działają jako samodzielne klipy;
- całość nie wygląda jak generyczny AI slop.

## Decyzje Przed Kodowaniem

- Przyjąć jako baseline serwera: RTX 5090 + 64 GB DDR5 RAM.
- Ustalić system operacyjny serwera.
- Ustalić, czy PostgreSQL i Redis działają na laptopie, serwerze, czy w obu miejscach.
- Ustalić, czy źródłem prawdy dla projektów jest laptop, serwer, czy repozytorium/synchronizowany katalog.
- Ustalić strategię backupu zatwierdzonych assetów i finalnych renderów.
- Ustalić limity pipeline'u: maksymalna liczba równoległych lekkich jobów i zawsze maksymalnie jeden ciężki job GPU.
- Wybrać dokładny lokalny runtime LLM.
- Wybrać pierwsze narzędzie do muzyki i wokalu.
- Wybrać workflow runner dla obrazu i video.
- Wybrać Next.js albo Vue dla UI.
- Ustalić, czy MVP zaczyna od importu audio czy lokalnego generowania.
- Zdefiniować pierwsze dwie stałe postacie.
- Przygotować pierwsze prompty do wygenerowania postaci w Codexie przez `gpt-image-2`.
- Zatwierdzić style guide kanału przed produkcją wielu odcinków.
