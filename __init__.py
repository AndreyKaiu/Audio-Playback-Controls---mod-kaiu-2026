from typing import Any, List, Tuple

import aqt
import aqt.sound
from aqt import gui_hooks, mw
from aqt.qt import *
from datetime import timedelta
from aqt.reviewer import Reviewer
from aqt.previewer import Previewer
from aqt.utils import showWarning, tooltip, qconnect
from aqt.webview import WebContent
from aqt.sound import av_player
from anki.cards import Card, CardId
import re
import json
from aqt.qt import QInputDialog, QLineEdit
from bs4 import BeautifulSoup
from aqt.webview import AnkiWebView
from aqt.webview import AnkiWebViewKind
from anki.sound import TTSTag, AV_REF_RE, AVTag, SoundOrVideoTag
import types
from anki.utils import checksum, is_win, tmpdir
from .store import JsonStore
from pathlib import Path
from aqt.qt import QMenu, QCursor, Qt, QShortcut, QKeySequence, QApplication


ADDON_VERSION = "1.3"
config = mw.addonManager.getConfig(__name__)
mw.addonManager.setWebExports(__name__, r"web/.*\.(css|js)")
base_path = f"/_addons/{mw.addonManager.addonFromModule(__name__)}/web"



store = None
def init_store() -> None:
    global store
    if store is None:
        addon_id = mw.addonManager.addonFromModule(__name__)
        data_dir = Path(mw.pm.profileFolder()) / "addon_data" / addon_id
        data_dir.mkdir(parents=True, exist_ok=True)
        store = JsonStore(data_dir / "AB.json")

gui_hooks.profile_did_open.append(init_store)

def get_file_data(filename: str) -> dict:
    return store.get(filename, {})

def set_file_field(filename: str, field: str, value) -> None:
    data = get_file_data(filename)
    data[field] = value
    store.set(filename, data)



_active_webviews = []

def on_card_review_webview_did_init(webview: AnkiWebView, kind):
    # Добавляем WebView для любых видов просмотра (REVIEW, PREVIEW, CARD_LAYOUT)
    # Можно фильтровать по kind, если нужно, но для простоты добавляем все
    if webview not in _active_webviews:
        _active_webviews.append(webview)

gui_hooks.card_review_webview_did_init.append(on_card_review_webview_did_init)


def send_js_to_all_reviewers(js_code: str):
    global _active_webviews
    for wv in _active_webviews[:]:
        try:
            if wv and wv.page() is not None:
                wv.eval(js_code)
                # wv.update()
            else:
                if wv in _active_webviews:
                    _active_webviews.remove(wv)
        except Exception:
            if wv in _active_webviews:
                _active_webviews.remove(wv)




def append_webcontent(webcontent: WebContent, context: Any) -> None:
    if isinstance(context, (Reviewer, Previewer)):
        webcontent.css.append(f"{base_path}/audio.css?v={ADDON_VERSION}")
        webcontent.js.append(f"{base_path}/audio.js?v={ADDON_VERSION}")
        
gui_hooks.webview_will_set_content.append(append_webcontent)

def extract_muted_fileortts(html):
    soup = BeautifulSoup(html, 'html.parser')
    result = []
    for parent in soup.find_all(class_='muteAudio'):
        for a in parent.find_all('a', class_='replay-button'):
            if 'soundLink' in a.get('class', []):
                src = a.get('data-fileortts')
                if src:
                    result.append(src)
    return result



def cleanTTS1024(text_tts: str) -> str:
    if not text_tts:
        return ""
    clean = text_tts
    clean = clean.replace('`', '').replace('"', '').replace('&', '').replace('<', '').replace('>', '')
    clean = clean.replace('\n', ' ').replace('\r', '') # Убираем переносы строк и лишние пробелы
    clean = re.sub(r'\s+', ' ', clean)
    clean = clean.strip()
    # Обрезка до 1024 символов с сохранением целых слов
    if len(clean) > 1024:
        trimmed = clean[:1024]
        last_space = trimmed.rfind(' ')
        if last_space != -1:
            clean = trimmed[:last_space].strip()
        else:
            clean = trimmed.strip()
    return clean


# needed to get the file name from "pycmd('play:'
_muted_fileortts = [] # All audio that is inside an element with the class "muteAudio" should not be played.

def inject_audio_fileortts(text: str, card, kind: str) -> str:
    global _muted_fileortts

    # print("inject_audio_fileortts")

    _muted_fileortts = []

    if 'data-fileortts="' in text:
        return text
    
    
    card.render_output()
    q_tags = card.question_av_tags()
    a_tags = card.answer_av_tags()

    def repl(match):
        full_tag = match.group(0)
        cmd = match.group(2)
        try:
            _, context, idx = cmd.split(":")
            idx = int(idx)
            tags = q_tags if context == "q" else a_tags
            if 0 <= idx < len(tags):
                filename = tags[idx].filename
            elif tags:
                filename = tags[0].filename
            else:
                filename = ""
        
        except Exception:
            filename = ""
            
        if filename == "":
            try:
                _, context, idx = cmd.split(":")
                idx = int(idx)
                tags = q_tags if context == "q" else a_tags
                if 0 <= idx < len(tags):
                    txt = tags[idx].field_text
                elif tags:
                    txt = tags[0].field_text
                else:
                    txt = ""
            except Exception:
                txt = ""
            if not(txt == ""):
                clean_txt = cleanTTS1024(txt)
                return full_tag.replace('<a', f'<a data-fileortts="/{clean_txt}"', 1)
            pass
        else:
            return full_tag.replace('<a', f'<a data-fileortts="{filename}"', 1)


    
    modified_text = re.sub(
        r'(<a[^>]*class="[^"]*soundLink[^"]*"[^>]*onclick="[^"]*pycmd\(\'(play:[^\']+)\'\)[^"]*"[^>]*>)',
        repl,
        text
    )

    # Теперь извлекаем имена для muteAudio из модифицированного HTML
    _muted_fileortts = extract_muted_fileortts(modified_text)
    # print("_muted_fileortts:", _muted_fileortts)
    return modified_text

gui_hooks.card_will_show.append(inject_audio_fileortts)



def on_av_player_will_play_tags(tags: list[AVTag], side: str, self):
    card = getattr(self, 'card', None)
    if card is None:
        return
    

    if isinstance(self, Reviewer):     
        card = self.card   
        if side == "question":
            q = card.question()
            side = "reviewQuestion"
        elif side == "answer":  
            q = card.answer()
            side = "reviewAnswer"
        else:
            return    

        q = self._mungeQA(q)     
        inject_audio_fileortts(q, card, side)

    elif isinstance(self, Previewer):
        card = self.card()
        txt = card.question(reload=True)
        ans_txt = card.answer()

        if self._state == "answer":            
            txt = card.answer()
        else:
            txt = card.question(reload=True)

        if side == "question":            
            side = "reviewQuestion"
        elif side == "answer":              
            side = "reviewAnswer"
        
        # txt = self.type_ans_preview_filter(txt, self._state)
        q = self.mw.prepare_card_text_for_display(txt)
        inject_audio_fileortts(q, card, side)




gui_hooks.av_player_will_play_tags.append(on_av_player_will_play_tags)



mpv_loop_file = config["Replay 1 Audio"] # False 
mpv_audio1_loop_count = config["audio1_loop_count"] #"0"
action_audio1_loop_count = None

mpv_loop_AudioList = config["Replay Audio-List"] # False 
mpv_audio_list_loop_count = config["audio_list_loop_count"] #"0" 
action_audio_list_loop_count = None


def updateColorLoop():    
    global mpv_loop_file, mpv_loop_AudioList 
    # print("UPDATECOLORLOOP")
    if mpv_loop_AudioList and mpv_loop_file:
        send_js_to_all_reviewers(f"if(window.color_loop_file_AND_AudioList) color_loop_file_AND_AudioList) window.color_loop_file_AND_AudioList();")  
    elif mpv_loop_AudioList:                                 
       send_js_to_all_reviewers(f"if(window.color_loop_AudioList) window.color_loop_AudioList();")
    elif mpv_loop_file:                
        send_js_to_all_reviewers(f"if(window.color_loop_file) window.color_loop_file();")
    else:
       send_js_to_all_reviewers(f"if(window.color_loop_reset) window.color_loop_reset();")
    

def on_reviewer_did_show_question_answer(card: Card):
    QTimer.singleShot(1000, lambda: updateColorLoop())

gui_hooks.reviewer_did_show_question.append(on_reviewer_did_show_question_answer)
gui_hooks.reviewer_did_show_answer.append(on_reviewer_did_show_question_answer)



_is_user_click = False

def on_pycmd_handler(handled: tuple[bool, Any], message: str, context: Any):
    global _is_user_click
    if message.startswith('play:'):
        _is_user_click = True
    return handled

gui_hooks.webview_did_receive_js_message.append(on_pycmd_handler)


original_pop_next = av_player._pop_next

def patched_pop_next(self):
    global _muted_fileortts, _current_filename

    while self._enqueued:
        
        # Берём первый элемент (не удаляя его пока, чтобы проверить)
        first = self._enqueued[0]
        # print("Type:", type(first))
        # print("Attr:", dir(first))
        filename = getattr(first, 'filename', None) # Получаем имя файла из AVTag
        field_text = getattr(first, 'field_text', None) 
        other_args = getattr(first, 'other_args', None)
        # print("patched_pop_next:filename=", filename)
        # print("patched_pop_next:field_text=", field_text)
        # print("patched_pop_next:other_args=", other_args)

        # print("patched_pop_next: str(_current_filename)=" + str(_current_filename))
        # print("patched_pop_next: filename=" + filename)

        
        if not self._is_user_click: # пользователь может кликать на любые файлы
            
            if filename is None or filename == "": # если это TTS который muteAudio
                other_args = getattr(first, 'other_args', None)
                if other_args is not None and any("muteAudio" in arg for arg in other_args):
                    # Найден аргумент, содержащий "muteAudio" – пропускаем
                    self._enqueued.pop(0)
                    continue
            
            # Если это временный файл (от TTS) – то берем из _current_filename до этого пришедший
            if _current_filename is not None and filename is not None and ("anki_temp" in filename or tmpdir() in filename):
                filename = _current_filename

            # print("patched_pop_next; in _muted_fileortts: str(_current_filename)=" + str(_current_filename))

            if filename and filename in _muted_fileortts:
                # Этот файл запрещён – удаляем его из очереди и пропускаем
                # print("Этот файл запрещён – удаляем его из очереди и пропускаем")
                self._enqueued.pop(0)
                continue
            
        # Разрешённый файл – обрабатываем как обычно
        if self.audio_list_loop_count is None:
            try:
                self.audio_list_loop_count = int(mpv_audio_list_loop_count) * len(self._enqueued)
            except Exception:
                self.audio_list_loop_count = 0

        if not mpv_loop_AudioList or len(self._enqueued) <= 1 or self.audio_list_loop_count is None:
            return self._enqueued.pop(0)
        else:
            if self.audio_list_loop_count > 0:
                self.audio_list_loop_count -= 1
                first = self._enqueued.pop(0)
                self._enqueued.append(first)
                return first
            else:
                return self._enqueued.pop(0)
    
    gui_hooks.av_player_did_end_playing(self.current_player)
    
    # Если очередь опустела (все элементы были запрещены)
    return None

av_player._pop_next = types.MethodType(patched_pop_next, av_player)




# Подмена clear_queue_and_maybe_interrupt
original_clear = av_player.clear_queue_and_maybe_interrupt

def patched_clear_queue_and_maybe_interrupt(self):
    global mpv_audio_list_loop_count, _is_user_click
    original_clear()
    self.audio_list_loop_count = None
    self._is_user_click = _is_user_click
    _is_user_click = False

av_player.clear_queue_and_maybe_interrupt = types.MethodType(
    patched_clear_queue_and_maybe_interrupt, av_player
)



def get_duration():
    try:
        return aqt.sound.mpvManager.get_property("duration")
    except Exception as e:
        return None
    
    

def get_time_pos():
    try:
        return aqt.sound.mpvManager.get_property("time-pos")
    except Exception as e:
        return None
  
   
def replay1AudioLoop():  
    global mpv_loop_file, mpv_loop_AudioList, mpv_audio1_loop_count
    # mw.reviewer.replayAudio() 
    mpv_loop_file = not mpv_loop_file
    mpv_audio1_loop_count = config["audio1_loop_count"] 
    
    try:        
        if mpv_loop_file:
            str_ab_loop_count = config["audio1_loop_count"] 
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)
        else:
            str_ab_loop_count = "inf"        
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)
    except Exception:
        pass
    
    
    if mpv_loop_file:    
        tooltip(f"<b><span style='color: red;'>ON.</span> Replay 1 Audio (Loop:{mpv_audio1_loop_count})</b>", period=3000)
    else:
        tooltip(f"<b><span style='color: blue;'>OFF.</span> Replay 1 Audio (Loop:{mpv_audio1_loop_count})</b>", period=3000)
        
    updateColorLoop()
               
    

def setABLoop():
    global mpv_loop_file, mpv_audio1_loop_count 
    aqt.sound.mpvManager.command("set_property", "ab-loop-a", "no")
    aqt.sound.mpvManager.command("set_property", "ab-loop-b", "no")
    aqt.sound.mpvManager.command("set_property", "ab-loop-count", mpv_audio1_loop_count)

    if not mpv_loop_file:
        return
    
    
    duration = get_duration()
    if duration is not None:
        if duration > 0.1:
            duration = duration - 0.05
        aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(0)) 
        aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(duration))
        
def on_av_player_did_begin_playing(player, tag):
    QTimer.singleShot(150, lambda: setABLoop())
    
    
 
  
def replayAudioListLoop():
    global mpv_loop_AudioList, mpv_loop_file, mpv_audio_list_loop_count 
    mpv_loop_AudioList = not mpv_loop_AudioList   
    mpv_audio_list_loop_count = config["audio_list_loop_count"]
    
    try:        
        if mpv_loop_file:
            str_ab_loop_count = config["audio1_loop_count"] 
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)    
        else:
            str_ab_loop_count = "inf"        
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)            
    except Exception:
        pass
    
    
    if mpv_loop_AudioList:    
        tooltip(f"<b><span style='color: red;'>ON.</span> Replay Audio-List (Loop:{mpv_audio_list_loop_count})</b>", period=3000)        
    else:
        tooltip(f"<b><span style='color: blue;'>OFF.</span> Replay Audio-List (Loop:{mpv_audio_list_loop_count})</b>", period=3000)   
        
    updateColorLoop()


d_lenAB = 0
def set_A():
    global _current_filename, d_lenAB    
    loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
    duration = get_duration()
    if duration is None or duration < 2:
        return
    
    str_ab_loop_count = ""    
    if mpv_loop_file:
        str_ab_loop_count = config["audio1_loop_count"] 
        aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)    
    else:
        str_ab_loop_count = "inf"        
        aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)
        
    mpv_time_pos_A = get_time_pos()
    if mpv_time_pos_A is not None:
        if (mpv_time_pos_A - 0.5) >= 0:
            mpv_time_pos_A = mpv_time_pos_A - 0.5
        aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(mpv_time_pos_A))        
        if loop_b is None or loop_b == "no" or int(loop_b) < mpv_time_pos_A:            
            mpv_time_pos_B = duration - 0.1  
            aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(mpv_time_pos_B))
        else:
            mpv_time_pos_B = float(loop_b)

        d_lenAB = mpv_time_pos_B - mpv_time_pos_A   
        
        time_string_A = str(timedelta(seconds=int(mpv_time_pos_A)))         
        time_string_B = str(timedelta(seconds=int(mpv_time_pos_B))) 
        if (duration - mpv_time_pos_B) >= 1:
            time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
        else:
            time_strind_D = "" 
            
        if mpv_time_pos_A >= 1:            
            smB = "..."
        else:
            smB = ""   

        if _current_filename and _current_filename != "":
            set_file_field(_current_filename, "A", str(mpv_time_pos_A)) 
            set_file_field(_current_filename, "B", str(mpv_time_pos_B))
            set_file_field(_current_filename, "d", str(d_lenAB))
       
        tooltip(f"<b>SET A Loop({str_ab_loop_count}) A-B: {smB}[<span style='color: red;'>{time_string_A}</span> - {time_string_B}]{time_strind_D}</b>", period=3000)     
           

     
def set_B():  
    global _current_filename, d_lenAB     
    loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
    duration = get_duration()
    if duration is None or duration < 2:
        return
        
    str_ab_loop_count = ""    
    if mpv_loop_file:
        str_ab_loop_count = config["audio1_loop_count"] 
        aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)    
    else:
        str_ab_loop_count = "inf"        
        aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)
        
    mpv_time_pos_B = get_time_pos()
    if mpv_time_pos_B is not None:
        if (mpv_time_pos_B + 0.5) < duration:
            mpv_time_pos_B = mpv_time_pos_B + 0.5
        aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(mpv_time_pos_B))        
        if loop_a is None or loop_a == "no" or int(loop_a) > mpv_time_pos_B:            
            mpv_time_pos_A = 0
            aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(mpv_time_pos_A))
        else:
            mpv_time_pos_A = float(loop_a)

        d_lenAB = mpv_time_pos_B - mpv_time_pos_A    
        
        time_string_A = str(timedelta(seconds=int(mpv_time_pos_A)))         
        time_string_B = str(timedelta(seconds=int(mpv_time_pos_B))) 
        if (duration - mpv_time_pos_B) >= 1:
            time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
        else:
            time_strind_D = "" 
            
        if mpv_time_pos_A >= 1:            
            smB = "..."
        else:
            smB = ""            

        if _current_filename and _current_filename != "":
            set_file_field(_current_filename, "A", str(mpv_time_pos_A)) 
            set_file_field(_current_filename, "B", str(mpv_time_pos_B))
            set_file_field(_current_filename, "d", str(d_lenAB))

        tooltip(f"<b>SET B Loop({str_ab_loop_count}) A-B: {smB}[{time_string_A} - <span style='color: red;'>{time_string_B}</span>]{time_strind_D}</b>", period=3000)     

 
    
def reset_AB():
    global _current_filename, d_lenAB
    aqt.sound.mpvManager.command("set_property", "ab-loop-a", "no")
    aqt.sound.mpvManager.command("set_property", "ab-loop-b", "no")

    d_lenAB = 0

    if _current_filename and _current_filename != "":
        set_file_field(_current_filename, "A", "")
        set_file_field(_current_filename, "B", "")
        set_file_field(_current_filename, "d", "0.0")
    
    tooltip(f"<span style='color: black;'><b>RESET A-B<b></span>", period=3000)


def reset_A():
    global _current_filename    
    aqt.sound.mpvManager.command("set_property", "ab-loop-a", "no")    

    if _current_filename and _current_filename != "":
        set_file_field(_current_filename, "A", "")
    
    tooltip(f"<span style='color: blue;'><b>RESET A<b></span>", period=3000)

def reset_B():
    global _current_filename    
    aqt.sound.mpvManager.command("set_property", "ab-loop-b", "no")    

    if _current_filename and _current_filename != "":
        set_file_field(_current_filename, "B", "")
    
    tooltip(f"<span style='color: blue;'><b>RESET B<b></span>", period=3000)
    


time_bookmark = 0
def set_a_bookmark():
    global time_bookmark, _current_filename
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return
            
        str_duration = str(timedelta(seconds=int(duration)))     
        
        timepos = get_time_pos()
        time_bookmark = timepos   
        if _current_filename and _current_filename != "":
            set_file_field(_current_filename, "m", str(timepos)) 
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        
        if loop_a != "no" and loop_b != "no" and timepos >= loop_a and timepos <= loop_b: 
            scolor = "red"
        else:
            scolor = "blue"
        tooltip(f"<b>SET A BOOKMARK:  Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass
    
    
def go_to_bookmark():
    global time_bookmark
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return
            
        if time_bookmark is not None and time_bookmark <= duration:
            aqt.sound.mpvManager.command("set_property", "time-pos", time_bookmark)
        else:
            return
        
        str_duration = str(timedelta(seconds=int(duration)))
        
        timepos = get_time_pos()
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        
        if loop_a != "no" and loop_b != "no" and timepos >= loop_a and timepos <= loop_b: 
            scolor = "red"
        else:
            scolor = "blue"
        tooltip(f"<b>GO TO BOOKMARK:  Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 
    except Exception: 
        pass


def go_to_00():    
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return

        aqt.sound.mpvManager.command("set_property", "time-pos", 0)
        
        str_duration = str(timedelta(seconds=int(duration)))
        
        timepos = get_time_pos()
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        
        if loop_a != "no" and loop_b != "no" and timepos >= loop_a and timepos <= loop_b: 
            scolor = "red"
        else:
            scolor = "blue"
        tooltip(f"<b>GO TO 00:00  Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 
    except Exception: 
        pass    


def go_to_next_audio():
    try:                
        duration = get_duration()    
        aqt.sound.mpvManager.command("set_property", "ab-loop-a", "no")
        aqt.sound.mpvManager.command("set_property", "ab-loop-b", "no")
        aqt.sound.mpvManager.command("set_property", "time-pos", duration-0.1)         
    except Exception: 
        pass    
    
          
def shift_AB_left():
    global _current_filename
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return
         
        str_ab_loop_count = ""    
        if mpv_loop_file:
            str_ab_loop_count = config["audio1_loop_count"] 
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)    
        else:
            str_ab_loop_count = "inf"        
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count) 
        
            
        str_duration = str(timedelta(seconds=int(duration)))     
        
        timepos = get_time_pos()    
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        if loop_a != "no" and  loop_b != "no":            
            if loop_a < 10:
                loop_a = 0                        
            else:
                dloop = loop_b - loop_a
                loop_a -= dloop
                loop_b -= dloop
            if loop_a < 0:
                loop_a = 0
            if loop_b < 0:
                loop_b = 0
             
            
            aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(loop_a))             
            aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(loop_b))     
            str_loop_a = str(timedelta(seconds=int(loop_a)))   
            str_loop_b = str(timedelta(seconds=int(loop_b)))
            
            if (duration - loop_b) >= 1:
                time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
            else:
                time_strind_D = "" 
                
            if loop_a >= 1:            
                smB = "..."
            else:
                smB = ""          
            
            if (timepos-1) < loop_a or (timepos+1) > loop_b:
                aqt.sound.mpvManager.command("set_property", "time-pos", loop_a)
                timepos = loop_a 
                str_timepos = str(timedelta(seconds=int(timepos)))                
                
            if _current_filename and _current_filename != "":
                set_file_field(_current_filename, "A", str(loop_a))
                set_file_field(_current_filename, "B", str(loop_b))    

            tooltip(f"<b>SHIFT [A-B] LEFT:  Loop({ab_loop_count}) A-B:[<span style='color: red;'>{str_loop_a} - {str_loop_b}</span>], pos: {str_timepos} / {str_duration}</b>", period=3000)    
            
        else:    
            scolor = "blue"
            tooltip(f"<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass
    
          
def shift_AB_right():
    global _current_filename
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return
         
        str_ab_loop_count = ""    
        if mpv_loop_file:
            str_ab_loop_count = config["audio1_loop_count"] 
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)    
        else:
            str_ab_loop_count = "inf"        
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count) 
        
            
        str_duration = str(timedelta(seconds=int(duration)))     
        
        timepos = get_time_pos()    
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        if loop_a != "no" and  loop_b != "no":            
            if duration - loop_b < 10:
                loop_b = duration - 0.1                        
            else:
                dloop = loop_b - loop_a
                loop_a += dloop
                loop_b += dloop
            if loop_a > duration:
                loop_a = duration
            if loop_b > duration:
                loop_b = duration 
            
            
            aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(loop_a))             
            aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(loop_b))     
            str_loop_a = str(timedelta(seconds=int(loop_a)))   
            str_loop_b = str(timedelta(seconds=int(loop_b)))
            
            if (duration - loop_b) >= 1:
                time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
            else:
                time_strind_D = "" 
                
            if loop_a >= 1:            
                smB = "..."
            else:
                smB = ""     

            if (timepos-1) < loop_a or (timepos+1) > loop_b:
                aqt.sound.mpvManager.command("set_property", "time-pos", loop_a)
                timepos = loop_a 
                str_timepos = str(timedelta(seconds=int(timepos))) 
                 
            if _current_filename and _current_filename != "":
                set_file_field(_current_filename, "A", str(loop_a))
                set_file_field(_current_filename, "B", str(loop_b))

            tooltip(f"<b>SHIFT [A-B] RIGHT:  Loop({ab_loop_count}) A-B:[<span style='color: red;'>{str_loop_a} - {str_loop_b}</span>], pos: {str_timepos} / {str_duration}</b>", period=3000)    
            
        else: 
            scolor = "blue"
            tooltip(f"<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass          


        

def shift_A_left():
    global _current_filename, d_lenAB
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return
         
        str_ab_loop_count = ""    
        if mpv_loop_file:
            str_ab_loop_count = config["audio1_loop_count"] 
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)    
        else:
            str_ab_loop_count = "inf"        
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count) 
        
            
        str_duration = str(timedelta(seconds=int(duration)))     
        
        timepos = get_time_pos()    
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        if loop_a != "no" and  loop_b != "no":            
            if loop_a < 10:
                loop_a = 0                        
            else:
                dloop = d_lenAB          
                loop_a -= dloop                
            if loop_a < 0:
                loop_a = 0
            if loop_b < 0:
                loop_b = 0 
             
            
            aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(loop_a))             
            aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(loop_b))     
            str_loop_a = str(timedelta(seconds=int(loop_a)))   
            str_loop_b = str(timedelta(seconds=int(loop_b)))
            
            if (duration - loop_b) >= 1:
                time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
            else:
                time_strind_D = "" 
                
            if loop_a >= 1:            
                smB = "..."
            else:
                smB = ""          
            
            if (timepos-1) < loop_a or (timepos+1) > loop_b:
                aqt.sound.mpvManager.command("set_property", "time-pos", loop_a)
                timepos = loop_a 
                str_timepos = str(timedelta(seconds=int(timepos)))                
                
            if _current_filename and _current_filename != "":
                set_file_field(_current_filename, "A", str(loop_a))
                set_file_field(_current_filename, "B", str(loop_b))
                    
            tooltip(f"<b>SHIFT [A] LEFT ([A-B]*2):  Loop({ab_loop_count}) A-B:[<span style='color: red;'>{str_loop_a}</span> - {str_loop_b}], pos: {str_timepos} / {str_duration}</b>", period=3000)    
            
        else:    
            scolor = "blue"
            tooltip(f"<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass
    
          
def shift_B_right():
    global _current_filename, d_lenAB
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return
         
        str_ab_loop_count = ""    
        if mpv_loop_file:
            str_ab_loop_count = config["audio1_loop_count"] 
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)    
        else:
            str_ab_loop_count = "inf"        
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count) 
        
            
        str_duration = str(timedelta(seconds=int(duration)))     
        
        timepos = get_time_pos()    
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        if loop_a != "no" and  loop_b != "no":            
            if duration - loop_b < 10:
                loop_b = duration - 0.1                        
            else:
                dloop = d_lenAB               
                loop_b += dloop
            if loop_a > duration:
                loop_a = duration
            if loop_b > duration:
                loop_b = duration 
             
            
            aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(loop_a))             
            aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(loop_b))     
            str_loop_a = str(timedelta(seconds=int(loop_a)))   
            str_loop_b = str(timedelta(seconds=int(loop_b)))
            
            if (duration - loop_b) >= 1:
                time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
            else:
                time_strind_D = "" 
                
            if loop_a >= 1:            
                smB = "..."
            else:
                smB = ""     

            if (timepos-1) < loop_a or (timepos+1) > loop_b:
                aqt.sound.mpvManager.command("set_property", "time-pos", loop_a)
                timepos = loop_a 
                str_timepos = str(timedelta(seconds=int(timepos))) 
                 
            if _current_filename and _current_filename != "":
                set_file_field(_current_filename, "A", str(loop_a))
                set_file_field(_current_filename, "B", str(loop_b))

            tooltip(f"<b>SHIFT [B] RIGHT ([A-B]*2):  Loop({ab_loop_count}) A-B:[{str_loop_a} - <span style='color: red;'>{str_loop_b}</span>], pos: {str_timepos} / {str_duration}</b>", period=3000)    
            
        else: 
            scolor = "blue"
            tooltip(f"<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass  



    
          
def shift_A_right():
    global _current_filename, d_lenAB
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return
         
        str_ab_loop_count = ""    
        if mpv_loop_file:
            str_ab_loop_count = config["audio1_loop_count"] 
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)    
        else:
            str_ab_loop_count = "inf"        
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count) 
        
            
        str_duration = str(timedelta(seconds=int(duration)))     
        
        timepos = get_time_pos()    
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        if loop_a != "no" and  loop_b != "no":     
            if d_lenAB < (loop_b - loop_a):                         
                dloop = d_lenAB
            else:
                dloop = (loop_b - loop_a)/2
            loop_a += dloop     
            if loop_a > duration:
                loop_a = duration
            if loop_b > duration:
                loop_b = duration 
             
            
            aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(loop_a))             
            aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(loop_b))     
            str_loop_a = str(timedelta(seconds=int(loop_a)))   
            str_loop_b = str(timedelta(seconds=int(loop_b)))
            
            if (duration - loop_b) >= 1:
                time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
            else:
                time_strind_D = "" 
                
            if loop_a >= 1:            
                smB = "..."
            else:
                smB = ""     

            if (timepos-1) < loop_a or (timepos+1) > loop_b:
                aqt.sound.mpvManager.command("set_property", "time-pos", loop_a)
                timepos = loop_a 
                str_timepos = str(timedelta(seconds=int(timepos))) 
                 
            if _current_filename and _current_filename != "":
                set_file_field(_current_filename, "A", str(loop_a))
                set_file_field(_current_filename, "B", str(loop_b))

            tooltip(f"<b>SHIFT [A] RIGHT ([A-B]/2):  Loop({ab_loop_count}) A-B:[<span style='color: red;'>{str_loop_a}</span> - {str_loop_b}], pos: {str_timepos} / {str_duration}</b>", period=3000)    
            
        else: 
            scolor = "blue"
            tooltip(f"<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass 


def shift_B_left():
    global _current_filename, d_lenAB
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return
         
        str_ab_loop_count = ""    
        if mpv_loop_file:
            str_ab_loop_count = config["audio1_loop_count"] 
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count)    
        else:
            str_ab_loop_count = "inf"        
            aqt.sound.mpvManager.command("set_property", "ab-loop-count", str_ab_loop_count) 
        
            
        str_duration = str(timedelta(seconds=int(duration)))     
        
        timepos = get_time_pos()    
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        if loop_a != "no" and  loop_b != "no":     
            if d_lenAB < (loop_b - loop_a):
                dloop = d_lenAB
            else:
                dloop = (loop_b - loop_a)/2            
            loop_b -= dloop                
            if loop_a < 0:
                loop_a = 0
            if loop_b < 0:
                loop_b = 0              
            
            aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(loop_a))             
            aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(loop_b))     
            str_loop_a = str(timedelta(seconds=int(loop_a)))   
            str_loop_b = str(timedelta(seconds=int(loop_b)))
            
            if (duration - loop_b) >= 1:
                time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
            else:
                time_strind_D = "" 
                
            if loop_a >= 1:            
                smB = "..."
            else:
                smB = ""          
            
            if (timepos-1) < loop_a or (timepos+1) > loop_b:
                aqt.sound.mpvManager.command("set_property", "time-pos", loop_a)
                timepos = loop_a 
                str_timepos = str(timedelta(seconds=int(timepos)))                

            if _current_filename and _current_filename != "":
                set_file_field(_current_filename, "A", str(loop_a))
                set_file_field(_current_filename, "B", str(loop_b))                
                
            tooltip(f"<b>SHIFT [B] LEFT ([A-B]/2):  Loop({ab_loop_count}) A-B:[{str_loop_a} - <span style='color: red;'>{str_loop_b}</span>], pos: {str_timepos} / {str_duration}</b>", period=3000)    
            
        else:    
            scolor = "blue"
            tooltip(f"<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass





audio_seek_N = None
def seek_backward_N() -> None:
    global audio_seek_N
    if audio_seek_N is None:
        audio_seek_N = int(config["audio_seek_N"])
    av_player.seek_relative(-audio_seek_N)
    gui_hooks.audio_did_seek_relative(mw.web, -audio_seek_N)

def seek_forward_N() -> None:
    global audio_seek_N
    if audio_seek_N is None:
        audio_seek_N = int(config["audio_seek_N"])
    av_player.seek_relative(audio_seek_N)
    gui_hooks.audio_did_seek_relative(mw.web, audio_seek_N)       


def seek_backward_1M() -> None:
    audio_seek_1M = 60
    av_player.seek_relative(-audio_seek_1M)
    gui_hooks.audio_did_seek_relative(mw.web, -audio_seek_1M) 

def seek_forward_1M() -> None:   
    audio_seek_1M = 60
    av_player.seek_relative(audio_seek_1M)
    gui_hooks.audio_did_seek_relative(mw.web, audio_seek_1M)  
    
    
    

def get_speed() -> float:
    return aqt.sound.mpvManager.command("get_property", "speed")


def get_default_speed() -> float:
    return float(config.get("default_speed", 1.0))

def get_default_my_speed() -> float:
    return float(config.get("default_my_speed", 1.5))

def get_speed_factor() -> float:
    return float(config.get("speed_factor", 10)) / 100


def add_speed(speed: float) -> None:
    aqt.sound.mpvManager.command("add", "speed", speed)
    tooltip(f"<b>Current Speed: <span style='color: red;'>{get_speed()}</span><br>({speed:+})</b>", period=3000)


def set_speed(speed: float) -> None:
    aqt.sound.mpvManager.command("set_property", "speed", speed)


def reset_speed() -> None:
    value = get_default_speed()
    set_speed(value)
    tooltip(f"<b>Reset Speed: <span style='color: red;'>{get_speed()}</span></b>", period=3000)
    send_js_to_all_reviewers(f"setAudioPlaybackRate1({json.dumps(value)});")
        
def set_my_speed() -> None:
    value = get_default_my_speed()
    set_speed(value)
    tooltip(f"<b>Set my Speed: <span style='color: red;'>{get_speed()}</span></b>", period=3000)
    
    send_js_to_all_reviewers(f"setAudioPlaybackRate2({json.dumps(value)});")


def speed_up() -> None:
    factor = get_speed_factor()
    add_speed(factor)
    
    send_js_to_all_reviewers(f"addAudioPlaybackRate({json.dumps(factor)});")
    


def slow_down() -> None:
    factor = -get_speed_factor()
    add_speed(factor)
    
    send_js_to_all_reviewers(f"addAudioPlaybackRate({json.dumps(factor)});")
    


# Глобальная переменная для запоминания последнего ввода
_last_seek_input = ""

def seek_to_time():
    global _last_seek_input

    # 1. Проверяем, что mpv активен и длительность доступна
    try:
        duration = aqt.sound.mpvManager.get_property("duration")
        current_time = aqt.sound.mpvManager.get_property("time-pos")
    except Exception:
        return

    if duration is None or duration <= 0:
        return
    if current_time is None:
        current_time = 0.0
       
    
    str_duration = str(timedelta(seconds=int(duration))) 

    active_window = QApplication.activeWindow()
    if active_window is None:
        active_window = mw

    timepos = get_time_pos()    
    str_timepos = str(timedelta(seconds=int(timepos)))
    
    loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
    loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
    
    if loop_a != "no":
        str_loop_a = str(timedelta(seconds=int(loop_a))) 
    else:
        str_loop_a = loop_a
        
    if loop_b != "no":
        str_loop_b = str(timedelta(seconds=int(loop_b)))
    else:
        str_loop_b = loop_b
        
    ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

    
    if loop_a != "no" and loop_b != "no" and timepos >= loop_a and timepos <= loop_b: 
        scolor = "red"
    else:
        scolor = "blue"

    time_bookmark_str = str(timedelta(seconds=int(time_bookmark)))    
    if time_bookmark <= 0:
        time_bookmark_str = ""            
    else:
        time_bookmark_str = "M:[" + time_bookmark_str + "], "

    # 2. Запрашиваем ввод с предзаполненным последним значением
    text, ok = QInputDialog.getText(
        active_window,
        "Seek to Time",
        f"""<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], {time_bookmark_str} pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>
                <br>Enter time (e.g. 50%, 1:30, 120, +10, -5:30, +5%):""",
        QLineEdit.EchoMode.Normal,
        _last_seek_input  # подставляем последний ввод
    )
    if not ok or not text:
        return

    text = text.strip()
    _last_seek_input = text  # сохраняем для следующего раза

    seconds = None
    sign = 1
    raw = text

    # Определяем, является ли ввод относительным (+/-)
    if text.startswith('+') or text.startswith('-'):
        sign = 1 if text.startswith('+') else -1
        raw = text[1:].strip()
        if not raw:
            tooltip(f"Missing value after +/-.", period=3000)
            return

    # 3. Парсим raw-часть (без знака)
    if '%' in raw:
        # Проценты
        try:
            percent = float(raw.replace('%', '').strip())
            seconds = (percent / 100.0) * duration
        except ValueError:
            tooltip(f"Invalid percentage format.", period=3000)
            return
    elif ':' in raw:
        # Время в формате M:S или H:M:S
        parts = raw.split(':')
        try:
            if len(parts) == 2:
                minutes = int(parts[0])
                secs = int(parts[1])
                seconds = minutes * 60 + secs
            elif len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                secs = int(parts[2])
                seconds = hours * 3600 + minutes * 60 + secs
            else:
                tooltip(f"Invalid time format. Use M:S or H:M:S.", period=3000)
                return
        except ValueError:
            tooltip(f"Invalid time format.", period=3000)
            return
    else:
        # Секунды (может быть дробное число)
        try:
            seconds = float(raw)
        except ValueError:            
            tooltip(f"Invalid number of seconds.", period=3000)
            return

    # 4. Применяем знак, если это относительное смещение
    if text.startswith('+') or text.startswith('-'):
        new_pos = current_time + sign * seconds
    else:
        new_pos = seconds  # абсолютная позиция

    # 5. Ограничиваем диапазоном [0, duration]
    if new_pos < 0:
        new_pos = 0
    elif new_pos > duration:
        new_pos = duration

    # 6. Отправляем команду mpv
    try:
        aqt.sound.mpvManager.command("set_property", "time-pos", new_pos)        
    except Exception as e:
        tooltip(f"Failed to seek: {e}", period=3000)


def seek_to_A():
    try:
        duration = get_duration()
        if duration is None: # or duration < 2:
            return
            
        str_duration = str(timedelta(seconds=int(duration)))     

        timepos = get_time_pos()    
        str_timepos = str(timedelta(seconds=int(timepos))) 
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")

        if loop_a == "no":
            tooltip(f"<b><span style='color: red;'>Error. Not set [A]</span></b>", period=3000)
            "Error. Not set [A]"
            return

        try:
            new_pos = loop_a 
            aqt.sound.mpvManager.command("set_property", "time-pos", new_pos)   
            timepos = new_pos      
            str_timepos = str(timedelta(seconds=int(timepos))) 
        except Exception as e:
            tooltip(f"Failed to seek: {e}", period=3000)
           
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        
        if loop_a != "no" and loop_b != "no" and timepos >= loop_a and timepos <= loop_b: 
            scolor = "red"
        else:
            scolor = "blue"
        tooltip(f"<b>AUDIO SEEK TO [A]:  Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass


    


def seek_to_B():
    try:
        duration = get_duration()
        if duration is None: # or duration < 2:
            return
            
        str_duration = str(timedelta(seconds=int(duration)))     

        timepos = get_time_pos()    
        str_timepos = str(timedelta(seconds=int(timepos))) 
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")

        if loop_b == "no":
            tooltip(f"<b><span style='color: red;'>Error. Not set [B]</span></b>", period=3000)
            "Error. Not set [B]"
            return

        try:
            new_pos = loop_b + 0.1
            if new_pos >= duration:
                new_pos = 0   
            aqt.sound.mpvManager.command("set_property", "time-pos", new_pos)   
            timepos = new_pos      
            str_timepos = str(timedelta(seconds=int(timepos))) 
        except Exception as e:
            tooltip(f"Failed to seek: {e}", period=3000)
            
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        
        if loop_a != "no" and loop_b != "no" and timepos >= loop_a and timepos <= loop_b: 
            scolor = "red"
        else:
            scolor = "blue"
        tooltip(f"<b>AUDIO SEEK TO [B]:  Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass



def my_pause_audio():
    try:
        if mw.reviewer:
            mw.reviewer.on_pause_audio()
    except Exception:
        pass
    
# Вспомогательная функция для преобразования значения из конфига в список строк
def normalize_shortcuts(raw):
    if isinstance(raw, str):
        return [raw] if raw else []
    elif isinstance(raw, list):
        return raw
    else:
        return []

# Список действий (label, raw_shortcut, callback)
actions = [
    ("Speed Up Audio", config["speed_up_shortcut"], speed_up),
    ("Slow Down Audio", config["slow_down_shortcut"], slow_down),
    ("Reset Audio Speed", config["reset_speed_shortcut"], reset_speed),
    ("Set my Audio Speed", config["set_my_speed_shortcut"], set_my_speed),
    ("Pause Audio", config["pause_audio_shortcut"], my_pause_audio),
    ("Set A", config["set_A_shortcut"], set_A),
    ("Set B", config["set_B_shortcut"], set_B),
    ("Reset A-B", config["reset_AB_shortcut"], reset_AB),
    ("Reset A", config["reset_A_shortcut"], reset_A),
    ("Reset B", config["reset_B_shortcut"], reset_B),
    ("Shift <<[A-B] left", config["shift [A-B] left shortcut"], shift_AB_left),
    ("Shift [A-B]>> right", config["shift [A-B] right shortcut"], shift_AB_right),
    ("Shift <<[A] left (+d)", config["shift [A] left (+d) shortcut"], shift_A_left),
    ("Shift [B]>> right (+d)", config["shift [B] right (+d) shortcut"], shift_B_right),    
    ("Shift [A]>> right (-d)", config["shift [A] right (-d) shortcut"], shift_A_right),
    ("Shift <<[B] left (-d)", config["shift [B] left (-d) shortcut"], shift_B_left),
    ("Audio seek +"+config["audio_seek_N"]+"s", config["audio_seek_backward_shortcut"], seek_backward_N),
    ("Audio seek -"+config["audio_seek_N"]+"s", config["audio_seek_forward_shortcut"], seek_forward_N),
    ("Audio seek -1m", config["audio_seek_backward_1M_shortcut"], seek_backward_1M),
    ("Audio seek +1m", config["audio_seek_forward_1M_shortcut"], seek_forward_1M),
    ("Audio seek set...", config["seek_to_time_shortcut"], seek_to_time),
    ("Audio seek to [A]", config["seek_to_[A]_shortcut"], seek_to_A),
    ("Audio seek to [B+0.1]", config["seek_to_[B+0.1]_shortcut"], seek_to_B),
    ("Set a bookmark", config["set_a_bookmark_shortcut"], set_a_bookmark),
    ("Go to bookmark", config["go_to_bookmark_shortcut"], go_to_bookmark),
    ("Go to 00:00", config["go_to_00_shortcut"], go_to_00),
    ("Go to Next Audio", config["go_to_next_audio_shortcut"], go_to_next_audio)
]

def add_state_shortcuts(state: str, shortcuts: List[Tuple[str, Callable]]) -> None:
    if state == "review":
        for label, raw_sc, cb in actions:
            for sc in normalize_shortcuts(raw_sc):
                shortcuts.append((sc, cb))
        for sc in normalize_shortcuts(config["audio1_Replay_shortcut"]):
            shortcuts.append((sc, replay1AudioLoop))
        for sc in normalize_shortcuts(config["audio_list_Replay_shortcut"]):
            shortcuts.append((sc, replayAudioListLoop))

def add_menu_items(viewer: Reviewer, menu: QMenu) -> None:
    global mpv_loop_AudioList, mpv_loop_file
    is_Reviewer = isinstance(viewer, Reviewer)
    if is_Reviewer:
        submenu = QMenu("Audio Playback Controls", menu)
    else:
        submenu = menu

    for label, raw_sc, cb in actions:        
        sc_list = normalize_shortcuts(raw_sc)
        display_label = label
        if len(sc_list) > 1:
            display_label = f"{display_label} → [{', '.join(sc_list[1:])}]"
        action = submenu.addAction(display_label)
        sc_list = normalize_shortcuts(raw_sc)
        if len(sc_list) == 1:            
            action.setShortcut(sc_list[0])
        elif len(sc_list) > 1:            
            action.setShortcuts(sc_list)
        qconnect(action.triggered, cb)

    # Replay 1 Audio
    display_label = "Replay 1 Audio (Loop:" + config["audio1_loop_count"] + ")"     
    sc_list = normalize_shortcuts(config["audio1_Replay_shortcut"])
    if len(sc_list) > 1:
        display_label = f"{display_label} → [{', '.join(sc_list[1:])}]"
    action_audio1_loop_count = submenu.addAction(display_label)
    if len(sc_list) == 1:
        action_audio1_loop_count.setShortcut(sc_list[0])
    elif len(sc_list) > 1:
        action_audio1_loop_count.setShortcuts(sc_list)
    action_audio1_loop_count.setCheckable(True)
    action_audio1_loop_count.setChecked(mpv_loop_file)
    qconnect(action_audio1_loop_count.triggered, replay1AudioLoop)

    # Replay Audio-List
    display_label = "Replay Audio-List (Loop:" + config["audio_list_loop_count"] + ")" 
    sc_list = normalize_shortcuts(config["audio_list_Replay_shortcut"])
    if len(sc_list) > 1:
        display_label = f"{display_label}  [{', '.join(sc_list[1:])}]"
    action_audio_list_loop_count = submenu.addAction(display_label)    
    if len(sc_list) == 1:
        action_audio_list_loop_count.setShortcut(sc_list[0])
    elif len(sc_list) > 1:
        action_audio_list_loop_count.setShortcuts(sc_list)
    action_audio_list_loop_count.setCheckable(True)
    action_audio_list_loop_count.setChecked(mpv_loop_AudioList)
    qconnect(action_audio_list_loop_count.triggered, replayAudioListLoop)

    if is_Reviewer:
        menu.addMenu(submenu)
    else:
        for label, raw_sc, cb in actions:
            for sc in normalize_shortcuts(raw_sc):
                QShortcut(QKeySequence(sc), viewer, activated=cb)
        for sc in normalize_shortcuts(config["audio1_Replay_shortcut"]):
            QShortcut(QKeySequence(sc), viewer, activated=replay1AudioLoop)
        for sc in normalize_shortcuts(config["audio_list_Replay_shortcut"]):
            QShortcut(QKeySequence(sc), viewer, activated=replayAudioListLoop)

       

def create_previewer_menu(previewer):    
    menu = QMenu(previewer)
    add_menu_items(previewer, menu)
    return menu

def add_previewer_context_menu(previewer):
    # Настраиваем контекстное меню
    previewer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    previewer.customContextMenuRequested.connect(
        lambda pos: show_previewer_menu(previewer, pos)
    )
    
    # Создаём меню и сохраняем его на previewer
    previewer._my_menu = create_previewer_menu(previewer)
    
    # Шорткат M для показа меню
    QShortcut(QKeySequence("M"), previewer, activated=lambda: show_my_menu(previewer))

def show_previewer_menu(previewer, pos):
    # При правом клике используем то же меню, но можно создать новое, если нужно
    # Просто показываем сохранённое меню
    previewer._my_menu.exec(QCursor.pos())

def show_my_menu(previewer):
    if hasattr(previewer, '_my_menu'):
        previewer._my_menu.exec(QCursor.pos())

gui_hooks.previewer_did_init.append(add_previewer_context_menu)





def on_profile_did_open() -> None:    
    if mw.reviewer and mw.reviewer.web:
        if mw.reviewer.web not in _active_webviews:
            _active_webviews.append(mw.reviewer.web)
            
    if aqt.sound.mpvManager:
        gui_hooks.reviewer_will_show_context_menu.append(add_menu_items)
        gui_hooks.state_shortcuts_will_change.append(add_state_shortcuts)
        set_speed(get_default_speed())
    else:
        showWarning(
            "This add-on only works with the mpv media player.",
            title="Audio Playback Controls",
        )


gui_hooks.profile_did_open.append(on_profile_did_open)
gui_hooks.av_player_did_begin_playing.append(on_av_player_did_begin_playing)



# Глобальные переменные для управления таймером
_timer = None
_current_filename = None  # имя активного файла



def on_play_will_play(tag):
    global _timer, _current_filename, time_bookmark, d_lenAB
    if isinstance(tag, TTSTag):
        field_text = tag.field_text
        clean = cleanTTS1024(field_text)
        filename = "/" + clean
        _current_filename = filename
        send_js_to_all_reviewers(f"window.setActiveButtons({json.dumps(filename)});")
        send_js_to_all_reviewers(f"window.ensureProgressText({json.dumps(filename)});")
        if _timer is None:
            _start_progress_updater()
    elif isinstance(tag, SoundOrVideoTag):
        filename = tag.filename
        # Если это временный файл (от TTS) – игнорируем
        if "anki_temp" in filename or tmpdir() in filename:
            return
        _current_filename = filename
        send_js_to_all_reviewers(f"window.setActiveButtons({json.dumps(filename)});")
        send_js_to_all_reviewers(f"window.ensureProgressText({json.dumps(filename)});")

        if _timer is None:
            _start_progress_updater()

    if _current_filename and _current_filename != "":
        data = get_file_data(_current_filename)            
        if data:
            time_bookmark = float(data.get("m", "0.0"))
            d_lenAB = float(data.get("d", "0.0")) 
            def setAB():
                try:                        
                    duration = get_duration()
                    str_duration = str(timedelta(seconds=int(duration)))  
                    loop_a = float(data.get("A", "0.0")) 
                    loop_b = float(data.get("B", str_duration))
                    aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(loop_b)) 
                    aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(loop_a)) 
                except Exception:
                    pass
            QTimer.singleShot(300, lambda: setAB())




def _start_progress_updater():
    global _timer
    if _timer is not None:
        return
    # Обновляем не реже, чем 1 секунду
    _timer = mw.progress.timer(500, _update_progress_safe, repeat=True)


def _update_progress_safe():
    try:
        _update_progress()
    except Exception:        
        pass
        
def _update_progress():
    global _timer, _current_filename
    try:
        if not _current_filename:
            if _timer:
                _timer.stop()
                _timer = None
            return 

        updateColorLoop()
            
        # print("_current_filename=" + _current_filename)
        
        duration = aqt.sound.mpvManager.get_property("duration")
        time_pos = aqt.sound.mpvManager.get_property("time-pos")
        is_paused = aqt.sound.mpvManager.get_property("pause")
        if is_paused is None or is_paused != True:
            is_paused = False
        
        if duration is None or time_pos is None:
            return

        if duration < 3:
            # Удаляем текст и останавливаем таймер
            send_js_to_all_reviewers(f"document.querySelectorAll('.replay-button[data-fileortts={json.dumps(_current_filename)}] .progress-text').forEach(el => el.remove());")
            
            
            if _timer:
                _timer.stop()
                _timer = None
            return

       
        time_str = str(timedelta(seconds=int(time_pos)))
        percent = round((time_pos / duration) * 100)        
        js = f"if(window.updateProgress) window.updateProgress({json.dumps(_current_filename)}, {json.dumps(time_str)}, {json.dumps(str(percent) + '%')}, {json.dumps(is_paused)});"        
        

        
        send_js_to_all_reviewers(js)
        
        
    except Exception: 
        pass
       



original_toggle_pause = av_player.toggle_pause

def patched_toggle_pause(self) -> None:
    global time_bookmark, _current_filename
    original_toggle_pause()
    
    try:
        duration = get_duration()
        if duration is None: # or duration < 2:
            return
            
        str_duration = str(timedelta(seconds=int(duration)))     
        
        timepos = get_time_pos()    
        str_timepos = str(timedelta(seconds=int(timepos)))
        
        loop_a = aqt.sound.mpvManager.get_property("ab-loop-a")
        loop_b = aqt.sound.mpvManager.get_property("ab-loop-b")
        
        if loop_a != "no":
            str_loop_a = str(timedelta(seconds=int(loop_a))) 
        else:
            str_loop_a = loop_a
            
        if loop_b != "no":
            str_loop_b = str(timedelta(seconds=int(loop_b)))
        else:
            str_loop_b = loop_b
            
        ab_loop_count = aqt.sound.mpvManager.get_property("ab-loop-count") 

        
        if loop_a != "no" and loop_b != "no" and timepos >= loop_a and timepos <= loop_b: 
            scolor = "red"
        else:
            scolor = "blue"

        time_bookmark_str = str(timedelta(seconds=int(time_bookmark)))    
        if time_bookmark <= 0:
            time_bookmark_str = ""            
        else:
            time_bookmark_str = "M:[" + time_bookmark_str + "], "                    
        
        tooltip(f"<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], {time_bookmark_str} pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass

av_player.toggle_pause = types.MethodType(patched_toggle_pause, av_player)
            
            

original_seek_relative = av_player.seek_relative 
def patched_seek_relative(self, secs: int) -> None:
    original_seek_relative(secs)
    QTimer.singleShot(330, lambda: _update_progress_safe())    
av_player.seek_relative = types.MethodType(patched_seek_relative, av_player)

    

def on_play_did_end_playing(player):
    global _timer, _current_filename
    # Сброс состояния
    if _timer:
        _timer.stop()
        _timer = None

    js_code = """
        // Убираем класс playing со всех кнопок
        document.querySelectorAll('.replay-button.playing').forEach(el => el.classList.remove('playing'));
        // Удаляем все тексты процентов
        document.querySelectorAll('.progress-text').forEach(el => el.remove());
    """
    # print("on_play_did_end_playing")
    send_js_to_all_reviewers(js_code)
    
        
    _current_filename = None

gui_hooks.av_player_will_play.append(on_play_will_play)
gui_hooks.av_player_did_end_playing.append(on_play_did_end_playing)

