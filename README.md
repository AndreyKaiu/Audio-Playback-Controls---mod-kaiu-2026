# Audio-Playback-Controls---mod-kaiu-2026
An add-on for Anka that adds many audio management features.

Modification of such a simple addon [Audio Playback Controls](https://ankiweb.net/shared/info/312734862)

To begin with, I added the ability to set both the normal speed (essentially slow) and the fast speed specified in the settings. Since it was convenient for me to control the arrows, the keys were assigned to them and an additional option was introduced to make a spacebar, there is a 0 next to it, it seemed more convenient to me if the spacebar is already occupied by turning over the card.

<img width="500" height="292" alt="image" src="https://github.com/user-attachments/assets/d6fbc970-ce0a-49f4-82fb-c766e4b70b26" />

The need to set a specific "A-B" playback interval is almost standard in media players. However, the following algorithm hasn't found interest among developers of other video and audio players: playing the "A-B" interval several times, then shifting the range, and then playing a new "A-B" interval again several times, and so on until the end of the file. I think this would be ideal for memorization. For now, everything is manual: you can play the "A-B" interval endlessly or set the desired number and then set a new "A-B" interval again. If you play endlessly and notice that you've learned something, you can shift the interval forward and learn the new part of the information. If you've learned the new information as well, you can shift back and try to connect the old with what you've learned.

<img width="518" height="639" alt="image" src="https://github.com/user-attachments/assets/fe0f6650-acd8-48e9-82c8-4ab8e5390db7" />

A small jump option has been added. Let's say you just heard a word and need to rewind it, it's easier to rewind 2 seconds (or however many seconds you specify in the settings). You can also jump to the exact position you want. A window will appear where you can specify a percentage, an exact value, or a relative value from the current position.

<img width="533" height="210" alt="image" src="https://github.com/user-attachments/assets/d6873cc6-87ba-474d-bb61-7287afffd4e1" />

Please note that to make it clear that a file is playing, I had to change the button design. I didn't want to change these buttons; they're familiar and don't take up much space in the text. However, I added the time and percentage (for short files, up to 3 seconds, they're not displayed because they don't make sense). The current file is detected, and the button currently playing is highlighted.

It's often important to create a bookmark, a location to return to if something isn't clear from a subsequent explanation. It's easier to do this with a dedicated button and then quickly return to it if something just doesn't stick. This is an alternative to the "A-B" playback of a range and is very useful for YouTube (there's a special extension). The advantage of using a bookmark is that you can constantly change the range depending on the complexity of the information you're studying.

And the last thing in the menu: this is exactly the functionality you asked for: infinite repeat. But the problem is that repeat can be for a single file (or a range of A-B repeats), or it can be for the entire file list. So there are two repeats here.
The first repeat is the entire list (the outer one, so the button color will change more).

<img width="84" height="80" alt="image" src="https://github.com/user-attachments/assets/769addd3-3748-4928-baf0-b31103ce6715" />

Second repeat: This repeats one file from the entire playlist. For example, you want to repeat each file in a row twice (set repeat 1), and the entire playlist just once (set repeat 0).

<img width="81" height="70" alt="image" src="https://github.com/user-attachments/assets/fb102211-0702-4123-8d4b-fd3ae416c4ac" />

Well, it could be both, so the button would look like this:

<img width="88" height="65" alt="image" src="https://github.com/user-attachments/assets/5322a4cd-e564-436b-9859-a9488788391c" />

You can change these styles in the addon folder, there is a css file there.

And it seems like a lot has been done, but users also want this option: how to prevent some files from playing in autoplay (when pressing the R button, too)?

So, they want it to be so that if a very long file is provided as an additional file, it's not needed for autoplay, but is needed if the user wants to learn something and clicks on it themselves. There are other options where it's not desirable to have everything voiced (at least a long TTS).

People have a solution: using JavaScript. It's possible and good, but it requires specialized knowledge and isn't perfect. Perhaps one day we'll see the implemented request to have a setting for each field, determining whether it should be played when the map is displayed. However, there are still complex cases where the map has a different number of audio files, and the order of the files is important—say, the text is followed by text, and some files shouldn't be played, while others should be. So, such files need to be marked somehow, or more precisely, wrapped in a tag. I chose the class name "muteAudio." If you write this in the card design, you could use:

```
{{Front}}
<span class="muteAudio">{{Sounds}}</span>
```

Then all sounds in the `{{Sounds}}` field will not play automatically on this side of the card.

The tag name doesn't have to be a standard one. For example, here I've wrapped it with a made-up `t1` tag to prevent the `Extra` field from autoplaying using `TTS`:

```
<t1 class="muteAudio">{{tts en_US:Extra}}</t1>
```

If you need to mute certain sounds on a specific card, then you need to change it not in the design, but in the field itself. You can do the same thing, the main thing is to have `class="muteAudio"`

On the card itself, if you want to use TTS to voice a large portion of the text just for reference, then you certainly don't need auto-voice. In that case, you'll need to do it a little differently:

```
[anki:tts lang=en_US class=muteAudio] On the card itself, if you want to use TTS to voice a large portion of the text just for reference, then you certainly don't need auto-voice. In that case, you'll need to do it a little differently: [/anki:tts]
```

I wrote `class=muteAudio` without quotes. The key word here is `muteAudio`, and you can replace `class` with something shorter and more convenient for you; it's not that important. Now such long text won't be voiced on this particular card, unless you write it all in the field, of course, and not in the design. Although I admit that the card design may contain explanations that certainly shouldn't be voiced during autoplay, someone wants to hear such information, so a button somewhere could have been included.

Since this is an add-on, keep in mind that this functionality won't work in Anki Droid or anywhere else. But the more people want to use custom algorithms, the more likely it is that this Anki algorithm will become the standard, and then Anki Droid will implement it.

P.S. Oh, and I forgot to show an example of the window that appears when you click actions. Let's say it's useful to press pause and get information about the file length and whether the range "A-B" is specified.

<img width="631" height="87" alt="image" src="https://github.com/user-attachments/assets/5dee94ba-2343-48a2-9f6d-b5dac64f85ca" />























Однако, скоростью управлять хорошо, но становится проблема когда аудио длиннее 10 секунд, тогда уже простая перемотка на 5 секунд вперед и назад не всегда удобна.





