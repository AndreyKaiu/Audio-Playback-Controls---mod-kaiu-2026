from typing import Any, List, Tuple

import aqt
import aqt.sound
from aqt import gui_hooks, mw
from aqt.qt import *
from datetime import timedelta
from aqt.reviewer import Reviewer
from aqt.previewer import Previewer
from aqt.utils import showWarning, tooltip
from aqt.webview import WebContent
from aqt import gui_hooks
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




ADDON_VERSION = "1.06"
config = mw.addonManager.getConfig(__name__)
mw.addonManager.setWebExports(__name__, r"web/.*\.(css|js)")
base_path = f"/_addons/{mw.addonManager.addonFromModule(__name__)}/web"


_active_webviews = []

def on_card_review_webview_did_init(webview: AnkiWebView, kind):
    # Добавляем WebView для любых видов просмотра (REVIEW, PREVIEW, CARD_LAYOUT)
    # Можно фильтровать по kind, если нужно, но для простоты добавляем все
    if webview not in _active_webviews:
        _active_webviews.append(webview)

# Подписываемся на хук
gui_hooks.card_review_webview_did_init.append(on_card_review_webview_did_init)


def send_js_to_all_reviewers(js_code: str):
    global _active_webviews
    for wv in _active_webviews[:]:
        try:
            if wv and wv.page() is not None:
                wv.eval(js_code)
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




mpv_loop_file = config["Replay 1 Audio"] # False 
mpv_audio1_loop_count = config["audio1_loop_count"] #"0"
action_audio1_loop_count = None

mpv_loop_AudioList = config["Replay Audio-List"] # False 
mpv_audio_list_loop_count = config["audio_list_loop_count"] #"0" 
action_audio_list_loop_count = None


def updateColorLoop():
    if mpv_loop_AudioList and mpv_loop_file:
        send_js_to_all_reviewers(f"color_loop_file_AND_AudioList();")  
    elif mpv_loop_AudioList:                                 
       send_js_to_all_reviewers(f"color_loop_AudioList();")
    elif mpv_loop_file:                
        send_js_to_all_reviewers(f"color_loop_file();")
    else:
       send_js_to_all_reviewers(f"color_loop_reset();")
    

def on_reviewer_did_show_question_answer(card: Card):
    QTimer.singleShot(1000, lambda: updateColorLoop())

gui_hooks.reviewer_did_show_question.append(on_reviewer_did_show_question_answer)
gui_hooks.reviewer_did_show_answer.append(on_reviewer_did_show_question_answer)



_is_user_click = False
def on_pycmd_handler(handled: tuple[bool, Any], message: str, context: Any):
    global _is_user_click
    if message.startswith('play:'):
        _is_user_click = True
    return (False, None)

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
            
            if filename and filename in _muted_fileortts:
                # Этот файл запрещён – удаляем его из очереди и пропускаем
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


mpv_time_pos_A = None    
mpv_time_pos_B = None

def set_A():
    global mpv_time_pos_A, mpv_time_pos_B     
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
                
        tooltip(f"<b>LOOP({str_ab_loop_count}) A-B: {smB}[<span style='color: red;'>{time_string_A}</span> - {time_string_B}]{time_strind_D}</b>", period=3000)     
           

     
def set_B():  
    global mpv_time_pos_A, mpv_time_pos_B     
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
                
        tooltip(f"<b>LOOP({str_ab_loop_count}) A-B: {smB}[{time_string_A} - <span style='color: red;'>{time_string_B}</span>]{time_strind_D}</b>", period=3000)     

 
    
def reset_AB():
    global mpv_time_pos_A, mpv_time_pos_B
    aqt.sound.mpvManager.command("set_property", "ab-loop-a", "no")
    aqt.sound.mpvManager.command("set_property", "ab-loop-b", "no")
    mpv_time_pos_A = None    
    mpv_time_pos_B = None
    tooltip(f"<span style='color: black;'><b>Reset A-B<b></span>", period=3000)
    


time_bookmark = 0
def set_a_bookmark():
    global time_bookmark
    try:
        duration = get_duration()
        if duration is None or duration < 2:
            return
            
        str_duration = str(timedelta(seconds=int(duration)))     
        
        timepos = get_time_pos()
        time_bookmark = timepos
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
    
    
          
def shift_AB_left():
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
             
            
            aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(loop_a))             
            aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(loop_b))     
            str_loop_a = str(timedelta(seconds=int(loop_a)))   
            str_loop_b = str(timedelta(seconds=int(loop_b)))
            
            if (duration - loop_b) >= 1:
                time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
            else:
                time_strind_D = "" 
                
            if mpv_time_pos_A >= 1:            
                smB = "..."
            else:
                smB = ""          
            
            if (timepos-1) < loop_a or (timepos+1) > loop_b:
                aqt.sound.mpvManager.command("set_property", "time-pos", loop_a)
                timepos = loop_a 
                str_timepos = str(timedelta(seconds=int(timepos)))                
                
                
            tooltip(f"<b>SHIFT [A-B] LEFT:  Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: red;'>{str_timepos}</span> / {str_duration}</b>", period=3000)    
            
        else:    
            scolor = "blue"
            tooltip(f"<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

    except Exception: 
        pass
    
          
def shift_AB_right():
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
             
            
            aqt.sound.mpvManager.command("set_property", "ab-loop-a", str(loop_a))             
            aqt.sound.mpvManager.command("set_property", "ab-loop-b", str(loop_b))     
            str_loop_a = str(timedelta(seconds=int(loop_a)))   
            str_loop_b = str(timedelta(seconds=int(loop_b)))
            
            if (duration - loop_b) >= 1:
                time_strind_D = "..." + str(timedelta(seconds=int(duration))) 
            else:
                time_strind_D = "" 
                
            if mpv_time_pos_A >= 1:            
                smB = "..."
            else:
                smB = ""     

            if (timepos-1) < loop_a or (timepos+1) > loop_b:
                aqt.sound.mpvManager.command("set_property", "time-pos", loop_a)
                timepos = loop_a 
                str_timepos = str(timedelta(seconds=int(timepos))) 
                 
            tooltip(f"<b>SHIFT [A-B] RIGHT:  Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: red;'>{str_timepos}</span> / {str_duration}</b>", period=3000)    
            
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
        
    strduration = str(timedelta(seconds=int(duration)))

    # 2. Запрашиваем ввод с предзаполненным последним значением
    text, ok = QInputDialog.getText(
        mw,
        f"Seek to Time (max: {strduration})",
        "Enter time (e.g. 50%, 1:30, 120, +10, -5:30, +5%):",
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


def my_pause_audio():
    try:
        if mw.reviewer:
            mw.reviewer.on_pause_audio()
    except Exception:
        pass
    

actions = [
    ("Speed Up Audio", config["speed_up_shortcut"], speed_up),
    ("Slow Down Audio", config["slow_down_shortcut"], slow_down),
    ("Reset Audio Speed", config["reset_speed_shortcut"], reset_speed),
    ("Set my Audio Speed", config["set_my_speed_shortcut"], set_my_speed),
    ("Pause Audio", config["pause_audio_shortcut"], my_pause_audio),
    ("Set A", config["set_A_shortcut"], set_A),
    ("Set B", config["set_B_shortcut"], set_B),
    ("Reset A-B", config["reset_AB_shortcut"], reset_AB),
    ("Shift [A-B] << left", config["shift [A-B] left shortcut"], shift_AB_left),
    ("Shift [A-B] >> right", config["shift [A-B] right shortcut"], shift_AB_right),
    ("Audio seek +"+config["audio_seek_N"]+"s", config["audio_seek_backward_shortcut"], seek_backward_N),
    ("Audio seek -"+config["audio_seek_N"]+"s", config["audio_seek_forward_shortcut"], seek_forward_N),
    ("Audio seek -1m", config["audio_seek_backward_1M_shortcut"], seek_backward_1M),
    ("Audio seek +1m", config["audio_seek_forward_1M_shortcut"], seek_forward_1M),
    ("Audio seek set...", config["seek_to_time_shortcut"], seek_to_time),
    ("Set a bookmark", config["set_a_bookmark_shortcut"], set_a_bookmark),
    ("Go to bookmark", config["go_to_bookmark_shortcut"], go_to_bookmark)
]


def add_state_shortcuts(state: str, shortcuts: List[Tuple[str, Callable]]) -> None:
    if state == "review":
        for label, shortcut, cb in actions:
            shortcuts.append((shortcut, cb))
        shortcuts.append((config["audio1_Replay_shortcut"],replay1AudioLoop))
        shortcuts.append((config["audio_list_Replay_shortcut"],replayAudioListLoop))


def add_menu_items(reviewer: Reviewer, menu: QMenu) -> None:
    global mpv_loop_AudioList, mpv_loop_file, action_audio1_loop_count, action_audio_list_loop_count    
    for label, shortcut, cb in actions:
        action = menu.addAction(label)
        action.setShortcut(shortcut)
        qconnect(action.triggered, cb)
    action_audio1_loop_count = menu.addAction("Replay 1 Audio (Loop:"+config["audio1_loop_count"]+")")
    action_audio1_loop_count.setShortcut(config["audio1_Replay_shortcut"])
    action_audio1_loop_count.setCheckable(True)
    action_audio1_loop_count.setChecked(mpv_loop_file)    
    qconnect(action_audio1_loop_count.triggered, replay1AudioLoop)
    
    action_audio_list_loop_count = menu.addAction("Replay Audio-List (Loop:"+config["audio_list_loop_count"]+")")
    action_audio_list_loop_count.setShortcut(config["audio_list_Replay_shortcut"])
    action_audio_list_loop_count.setCheckable(True)
    action_audio_list_loop_count.setChecked(mpv_loop_AudioList)
    qconnect(action_audio_list_loop_count.triggered, replayAudioListLoop)
    

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
    global _timer, _current_filename
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







def _start_progress_updater():
    global _timer
    if _timer is not None:
        return
    # Обновляем каждую секунду
    _timer = mw.progress.timer(1000, _update_progress_safe, repeat=True)


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
            
    
        
        duration = aqt.sound.mpvManager.get_property("duration")
        time_pos = aqt.sound.mpvManager.get_property("time-pos")
        
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
        js = f"window.updateProgress({json.dumps(_current_filename)}, {json.dumps(time_str)}, {json.dumps(str(percent) + '%')});"        
        
        send_js_to_all_reviewers(js)
        
        
    except Exception: 
        pass
       



original_toggle_pause = av_player.toggle_pause

def patched_toggle_pause(self) -> None:
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
        tooltip(f"<b>Loop({ab_loop_count}) A-B:[{str_loop_a} - {str_loop_b}], pos: <span style='color: {scolor};'>{str_timepos}</span> / {str_duration}</b>", period=3000) 

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

