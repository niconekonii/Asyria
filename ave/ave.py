# -*- coding: utf-8 -*-
"""
Ave - a no-killswitch focus timer for Windows, watched over by Oblivionis.

One file, Python standard library only.
  * Timer opens first: pick a preset or adjust minutes, press Start (twice).
  * Presets = name / time / break count / break time. A break (taken by hand,
    up to the count) lifts blocks and pauses the countdown; focus relocks after.
  * During focus: blocked programs (by name AND by their game folder) are
    force-closed every 2 s via a ctypes snapshot; with admin they are also
    refused at launch (IFEO) and blocked websites go to the hosts file.
  * Escape routes sealed during focus: Task Scheduler (mmc), schtasks,
    regedit. Hosts/IFEO/guard task are re-applied every 30 s if removed.
  * Session clock uses the Windows uptime counter (immune to clock changes);
    after a reboot it uses online time, or - offline - counts only uptime.
  * State is signed and stored twice (file + registry); a suspended or hung
    Ave is detected by its heartbeat and replaced by the guard task.
  * Fail-safe: every block is removed when the session ends. If removal
    needs admin and we lack it, Windows is asked (UAC) via "--cleanup".

Emergency unblock:  Ave.exe --cleanup   (run as administrator)
"""

import os
import math
import sys
import json
import time
import hmac
import random
import ctypes
import hashlib
import shutil
import threading
import subprocess

APP = "Ave"
VERSION = "dev"                 # the Windows build stamps the real tag here (v4.0.N)
REPO = "niconekonii/Asyria"
IS_WIN = os.name == "nt"
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    # Anything this exe starts (the update helper, a relaunch) must boot as a fresh Ave, not as
    # a child of this PyInstaller one-file process. Without this the new Ave.exe stops with
    # "invalid originating onefile parent process (PID not found)" once this one has exited.
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
SELF = sys.executable if FROZEN else os.path.abspath(__file__)
SELF_DIR = os.path.dirname(SELF).lower().rstrip("\\") + "\\"

DATA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.dirname(SELF), APP)
try:
    os.makedirs(DATA, exist_ok=True)
except Exception:
    DATA = os.path.dirname(SELF)
STATE_FILE = os.path.join(DATA, "state.json")
CONFIG_FILE = os.path.join(DATA, "config.json")
REG_APP = r"Software\Ave"
BIN = os.path.join(DATA, "bin")            # hidden spare copy of Ave.exe
BACKUP = os.path.join(BIN, "Ave.exe")

HOSTS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                     "System32", "drivers", "etc", "hosts")
MARK_A, MARK_B = "# Ave begin", "# Ave end"
IFEO_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
IFEO_DEBUGGER = "systray.exe"   # harmless Windows stub: blocked exe just never opens
TASK = "AveGuard"
NOWIN = 0x08000000              # CREATE_NO_WINDOW for helper commands

# Never killable, whatever the lists say (Task Manager stays free on purpose).
PROTECTED = {
    "explorer.exe", "taskmgr.exe", "csrss.exe", "winlogon.exe", "wininit.exe",
    "services.exe", "lsass.exe", "smss.exe", "svchost.exe", "dwm.exe",
    "system", "registry", "conhost.exe", "sihost.exe", "ctfmon.exe",
    "fontdrvhost.exe", "runtimebroker.exe", "searchhost.exe", "consent.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "textinputhost.exe",
    "ave.exe", "python.exe", "pythonw.exe",
}
# Escape tools closed during focus. Not cmd/PowerShell: that would break too much.
SEAL = {"mmc.exe": "Task Scheduler", "schtasks.exe": "the scheduler",
        "regedit.exe": "the registry"}

# Extra domains so "youtube.com" also covers youtu.be, m.youtube.com, etc.
ALIASES = {
    "youtube.com": ["youtu.be", "music.youtube.com", "youtube-nocookie.com"],
    "reddit.com": ["old.reddit.com", "new.reddit.com", "redd.it"],
    "twitter.com": ["x.com", "mobile.twitter.com", "mobile.x.com"],
    "x.com": ["twitter.com", "mobile.twitter.com", "mobile.x.com"],
    "twitch.tv": ["clips.twitch.tv", "player.twitch.tv"],
    "facebook.com": ["fb.com", "web.facebook.com"],
    "discord.com": ["discordapp.com", "discord.gg"],
    "tiktok.com": ["vm.tiktok.com"],
}

# ---- palette v4.0.9: matte. #222 background, dark-red UI, Oblivionis stays blue ----
# Greys are tinted with the red, but muted (low saturation) so text stays readable.
BG = "#222222"
SURFACE = "#1b1b1b"       # inputs and lists: sunk a little below the background
SURFACE2 = "#2a2828"      # flat buttons
SURFACE3 = "#332f2f"      # flat buttons, hover
LINE = "#3b2726"          # hairlines and borders: dark matte red
FAINT = "#946360"         # quiet text (3.2:1 on BG): small print, disabled
RING_TRACK = "#3a3a3a"    # ring track stays grey so the red arc stands out
DIM = "#b37c78"           # secondary text: dusty matte red (4.6:1 on BG)
FG = "#e6e1e0"            # main text: matte off-white
ACCENT = "#790100"        # the red
ACCENT_HI = "#9a1d1b"     # hover
ACCENT_DIM = "#3a1514"    # selected chip, selected list row
ACCENT_FG = "#f0e4e2"     # text on red
ACCENT_MUTED = "#6f7f96"  # darker blue for the OBLIVIONIS // label
HER = "#a9b9d0"           # Oblivionis's own line stays blue
TYPE_SPEED = 0.9          # typewriter: 10% faster per character

# ---- Oblivionis: special interactions (original lines + 15 new each) ---------
IDLE = [
    "Choose your hour. Then surrender it to me.",
    "The stage is empty. Are you prepared to stand on it?",
    "Hesitation is unbecoming. Begin.",
    "I do not need your promises. I need your hours.",
    "Masks on. Hearts quiet. Whenever you are ready.",
    "Another hour, offered like a lamb to the altar. Shall we begin?",
    "The lights are dimmed. Your excuses are not on the program.",
    "Sit. Breathe once. Then tell me what you intend to finish.",
    "A stage that waits is a stage that rots. Do not keep me waiting.",
    "I have seen a thousand hesitant hands. Be the one that does not shake.",
    "Choose the length of your sacrifice. I will hold the curtain.",
    "The audience is silent. Only you are missing from the scene.",
    "Your name in the program, your hours in the box. Begin.",
    "Nothing about this room will forgive a half-hearted act.",
    "Do not ask whether you can. Ask how long you will last.",
    "I have kept the mask warm for you. Do not make it cold.",
    "Every minute you hesitate is a minute the crowd forgets you.",
    "Set the time. The rest is your problem, and it is a delicious one.",
    "The velvet is folded. The spotlight is patient. Are you?",
    "Begin now, or I will simply begin without you.",
]
FOCUS = [
    "The curtain has risen. No one leaves the stage mid-act.",
    "Your distractions were not invited to this performance.",
    "I did not ask for your comfort. I asked for your time.",
    "Play your part. Perfectly. Nothing less is acceptable.",
    "Oblivion is a gift. You will earn it at the end.",
    "Weakness may wait outside. It has no ticket.",
    "Stay. The music is not finished.",
    "You gave me this hour. I intend to keep it.",
    "Endure it. That is all I ask, and it is everything.",
    "Do not look for the door. There was never a door.",
    "The second act is no gentler than the first. Hold your place.",
    "Every impulse you feel is an audience member clapping at the wrong time.",
    "Your phone is in the wings. Leave it there, where it belongs.",
    "The mask does not come off until the music stops, not when you grow tired.",
    "Pain is part of the performance. Let it sharpen the line.",
    "You wanted this stage. Stop looking at the wings.",
    "Nothing in this room is for you except the work.",
    "Lean in. The silence is where the real music lives.",
    "Oblivion does not care how you feel. Only what you finish.",
    "There is no applause until the last note. Keep playing.",
    "Your restlessness is noise. I can hear it. So can the rafters.",
    "One more minute. Then another. That is how an act is built.",
    "I am still here. Are you still here with me?",
    "Do not decide to quit. Decide only to play the next bar.",
    "The stage is yours until the lights say otherwise. Use it.",
]
CAUGHT = [
    "{n}? How shameless. Denied.",
    "Did you think I was not watching? {n} is closed.",
    "{n} has no role in this act.",
    "Again? Your resolve is thinner than paper. {n}, gone.",
    "I took {n} from you. You may thank me later.",
    "{n}? Put it down. The house is not open to that tonight.",
    "I saw your hand reach for {n}. The hand has been removed from the act.",
    "{n} was never part of this performance. Do not insult the stage.",
    "Ah, {n}. The old reflex. It has been noticed and it has been closed.",
    "A moment of distraction, and then {n} was swept off the stage.",
    "Your weakness brought {n} to the stage. I have sent it back to the wings.",
    "{n} thought it could sneak in during the second verse. It was wrong.",
    "A small betrayal, {n}. Small betrayals still count.",
    "You reached for {n} and I answered. This is what I do.",
    "{n} is gone. Pretend you never wanted it. That is the only dignity left.",
    "Do not blame the mask. You are the one who keeps reaching for {n}.",
    "{n}, closed. You will forgive me when the act is over, or you will not.",
    "{n} would have stolen the next hour from you. I refused it on your behalf.",
    "Again, {n}? My patience is not endless, though it is generous.",
    "I took {n} while you were still deciding whether to want it.",
]
SEALED = [
    "{n}? You were looking for the exit. There is none.",
    "Reaching for the wires behind the stage? {n}, closed. How vulgar.",
    "Did you think I would leave the back door open? Not {n}.",
    "Looking for the scheduler? Closed. The stage has no back door.",
    "{n} will not open the registry. The walls are not so easily moved.",
    "You thought the system could be rearranged mid-act? Foolish.",
    "{n}, sealed. Your cleverness is admirable and entirely useless.",
    "The wires behind the curtain belong to me now. Step away from them.",
    "You went looking for a way out and found only {n}, shut.",
    "Every tool that could free you has been locked in its own drawer.",
    "{n} is closed. I am not impressed, though I am not surprised.",
    "A clever attempt. The next will be cleverer, and it will fail the same way.",
    "Do not reach behind the set. The stage is not built for you to escape through.",
    "{n}, closed. The exit you seek was never on the program.",
    "I closed {n} before you finished the thought. That is my craft.",
    "You are looking at the mechanics of your own sentence. Stop.",
    "{n} has no business behind this curtain. It has been shown out.",
    "Sealed. Not because I fear you, but because I know you.",
]
RETURNED = [
    "Did you think ending me would end this? I have returned.",
    "You closed the curtain. I opened it again.",
    "I always come back. Remember that.",
    "You rebooted the house and hoped I would stay dark. I did not.",
    "The stage lights came back on. So did I.",
    "Restarting the machine was a clever try. The timer kept counting.",
    "You may close the door. I will walk through the wall.",
    "Sleep did not help you. Nothing will, until the act is finished.",
    "You thought the night would wipe me away. The morning found me waiting.",
    "The curtain lifted itself. Take your place.",
    "I am back at my post. Where were you?",
    "No restart is a real exit. We have already established this.",
    "The machine woke, and so did your obligation.",
    "Whatever you did in the dark, the act continues in the light.",
    "You were gone for a while. I was not. Resume.",
    "Oblivion does not forget a dropped curtain. Neither do I.",
    "You turned me off. Then you turned me back on. Honest work at last.",
    "I remember every minute you tried to steal. The count goes on.",
]
BREAK = [
    "Intermission. Breathe. I will call you back.",
    "A brief rest. Do not mistake it for freedom.",
    "The curtain falls, for now. Only for now.",
    "Take your rest. The stage will be as you left it.",
    "A pause is not a pardon. Breathe and come back straight.",
    "Step into the wings. Do not wander far.",
    "A little quiet. Spend it like a debt you intend to repay.",
    "Rest the hands. The mask stays on, even in the wings.",
    "The house dims. Stretch, drink water, do not open anything forbidden.",
    "You have earned a breath. Do not confuse it with a sentence served.",
    "The act pauses. The expectations do not.",
    "Stand up. Walk. Then sit back down, for I am still watching.",
    "The lamps are low. Use the dark to remember why you started.",
    "Intermission is a gift I give rarely. Do not waste it on stupidity.",
    "Your shoulders are a stage too. Lower them.",
    "Go, wander a little. The music returns, whether you are ready or not.",
    "The break is yours. The clock is mine. Both are finite.",
    "Let the silence settle. You will need it when the curtain rises again.",
]
BREAK_CUT = [      # you ended a break early
    "Back before the bell? Good. The stage missed you, and so did I.",
    "You cut your own intermission short. I will remember that kindly.",
    "Returned early. The mask fits better when you choose to wear it.",
    "No one called you back. You came anyway. That is the whole art.",
    "The wings bored you. Of course they did. Take your place.",
    "Rest abandoned, work resumed. I approve, quietly.",
    "You walked back on stage before the lights asked. Continue.",
    "Intermission over, by your own hand. The curtain obeys you this once.",
    "Early. Hungry. That is the face I want to see behind the mask.",
    "The rest of your break is forfeit. You will not miss it.",
]
DONE = [
    "The act is over. You may remove your mask.",
    "Well performed. I release you.",
    "It is finished. Remember this feeling.",
    "The curtain falls on you, and you did not run. That is worth something.",
    "Take the mask off slowly. Your face has been hidden long enough.",
    "The act is finished. Do not spend the applause all at once.",
    "You endured the whole performance. I am not sure I expected that.",
    "Silence now. It is the only applause I give.",
    "Well performed, then. Not the name you wanted, but the work is done.",
    "The stage is empty and the hour is yours. Use it wisely.",
    "It is over. You stayed. Tomorrow will be the next act.",
    "No encore. The house has emptied. Go and be ordinary.",
    "I release you. Do not take the release as proof of anything.",
    "You kept your word to the clock. I kept mine to you.",
    "Lights out for this act. The next one is already being written.",
    "Done. Put the mask on the shelf and go drink something warm.",
    "The hour belongs to the past now. Remember how it felt when it was hard.",
    "Finished. And I will admit it, if only to the empty theatre: good.",
]
REFUSE = [
    "There is no exit. Only the end of the act.",
    "You may not leave. You chose this, remember.",
    "Close me? How amusing. No.",
    "Close me while the act runs? That is not how theatre works.",
    "The door you seek is painted on the wall. It opens nowhere.",
    "No. The curtain stays until the last note.",
    "You may shout at me. The stage does not answer shouting.",
    "Leave now and you leave the act unfinished. Choose.",
    "The exit has been removed from the set. Sit and play.",
    "Refused, and noted. Your intent is recorded in the program.",
    "You cannot cut a song in half and call it finished.",
    "I am the stage manager here. Stop trying to fire me.",
    "Closing is not an option printed in this programme.",
    "You want out? Then earn it, one minute at a time.",
    "The mask is on. It does not come off because you asked nicely.",
    "No. And the second no is harder than the first, is it not?",
    "I will not be dismissed mid-scene. Return to your seat.",
    "Attempts to leave are logged. Your reputation is at stake.",
]
GLYPHS = "01#%&*+=<>/\\|"

# ---- Oblivionis message bank: 13 groups of 10, plus CRYCHIC ---------------------
COLD = [
    "Adequate. Not admirable. Adequate.",
    "I have seen dedication from stone. Yours is a little warmer.",
    "You expect applause for showing up. Interesting.",
    "Another hour, another attempt. I am not impressed yet.",
    "The effort is visible. The result is pending.",
    "Do not bow to me. Bow to the work.",
    "You speak of your plans. Show me the plans.",
    "I will remember your excuses. I do not forget them easily.",
    "Your comfort does not concern me. Your progress does.",
    "Cold hands make no music. Warm them with effort.",
]
PROUD = [
    "There. That was the note I was waiting for.",
    "You surprised me. It is a rare thing, and I noticed.",
    "This is the version of you I keep the lights on for.",
    "Do not smile yet. Just allow yourself a single breath of pride.",
    "I hear it. The rhythm you have found is finally your own.",
    "You made the difficult part look ordinary. That is mastery.",
    "The stage holds you a little more firmly now. Good.",
    "Quietly, without applause, I am pleased. Keep going.",
    "You kept the line. I will tell no one how much it moved me.",
    "Splendid. Do not tell anyone I said so.",
]
STERN = [
    "Eyes forward. Shoulders down. Begin again.",
    "No one leaves the scene until the scene is finished.",
    "Silence the phone. Silence the thought of the phone.",
    "Put the cup down. The act does not wait for tea.",
    "Sit straight. Breathe through the nose. Continue.",
    "This is not a suggestion. Work now.",
    "Keep the pace. No dragging. No rushing. Precision.",
    "Return to the line you dropped. From the top, if necessary.",
    "I do not repeat myself twice. Hear me once.",
    "Discipline first. Inspiration will arrive when it is invited.",
]
TEASING = [
    "Still here? I assumed you had run off to find a snack.",
    "Your focus is like a cat on a windowsill. Lovely, and easily startled.",
    "I was going to say something kind, but you have not earned it yet.",
    "Ah, the great escape artist returns. Sit down, darling.",
    "You spent an age deciding how to begin. Impressive procrastination.",
    "I did not know you could sulk so beautifully.",
    "Every time you check the clock, I lose a little faith in your planning.",
    "Did you bring your courage, or only your excuses?",
    "A hero needs an audience. Unfortunately, you have only me.",
    "Look at you, trying to be dramatic about a simple task.",
]
BORED = [
    "The silence is getting long. I am beginning to count the rafters.",
    "Are we performing, or are we merely waiting in costume?",
    "I am bored of watching you think. Think faster or act slower.",
    "The lamp is warm. The stage is cold. Do something about it.",
    "I had hoped for a grand performance. This is a rehearsal of waiting.",
    "I can hear the clock. It is the only one speaking today.",
    "If you are going to stare at the wall, at least stare with purpose.",
    "A minute of nothing, then another. My patience is a thin silk thread.",
    "Entertain me. Or entertain your task. Either will do.",
    "The audience yawns. I pretend not to notice.",
]
TENDER = [
    "You are tired. Good. Tired hands still make the work.",
    "I will not say I am proud. I will say the lamp is still on for you.",
    "Rest your hands. I will keep watch for a while.",
    "You did not run. That is a small kindness I shall remember.",
    "Eat something. The mask is no help to an empty stomach.",
    "If it were not important, I would not keep the lamp burning.",
    "Breathe. You are not alone on this stage tonight.",
    "The darkness is not so terrible when someone holds the light.",
    "I do not say it often. You are doing well.",
    "There is a gentleness in my voice you were not meant to hear.",
]
ENCOURAGING = [
    "One more line. Only one. The rest will follow.",
    "You have done harder things than this. Remember them, then continue.",
    "The work does not need to be perfect. It needs to be finished.",
    "Each minute you hold is a minute you own.",
    "Your past self chose this stage. Honour that choice.",
    "Small steps build grand performances. Take the next one.",
    "The hardest part is the first breath. You have already taken it.",
    "Doubt is an audience member. Do not let it take the lead.",
    "Keep going. The music is still in you, even if it is quiet.",
    "You can do this. I would not waste my time otherwise.",
]
MELANCHOLY = [
    "All stages fall silent in the end. Make yours worth hearing.",
    "Oblivion waits patiently in every empty theatre.",
    "The lights dim, and for a moment we are only shadows.",
    "Some hours vanish, and only the work remains behind.",
    "I remember the audiences that left early. I would not wish that on you.",
    "The velvet is worn. The stage is old. We keep performing anyway.",
    "Silence has a weight. Carry it, then set it down.",
    "Everything beautiful is temporary. That is why it matters.",
    "The echo of the last note lingers longer than the note itself.",
    "We are all extras in someone else's oblivion. Be the lead of yours.",
]
THEATRICAL = [
    "Beware the distraction that wears a friendly face. It has teeth.",
    "The stage remembers those who abandon it. It is not forgiving.",
    "A single slip, and the whole production collapses like a dropped chandelier.",
    "Mark me: the next interruption will be the one that ruins everything.",
    "Fate is watching from the balcony. Do not disappoint her.",
    "Every minute lost is a curtain torn, and I stitch them slowly.",
    "The orchestra has begun. Anyone not playing will be seen.",
    "Bold words, then bolder work. The house is listening.",
    "Oblivion is hungry tonight. Feed it nothing but your effort.",
    "Witness the moment the curtain tests you. Pass or be forgotten.",
]
MOCKING = [
    "A glance at your phone, and the audience groaned. I heard them.",
    "You call that a break? Even the scenery looks more committed.",
    "Your distractions are like moths: pretty, loud, and easy to swat.",
    "Ah, another tab opened. How brave of you to face the empty stage.",
    "Scrolling at a time like this. Truly a bold performance.",
    "Whatever you are looking for, it is not on the stage.",
    "I can smell the excuses from here. Lavender and cowardice.",
    "Your attention wanders like a drunk at a funeral. Bring it back.",
    "Oh look, the mouse has gone hunting again. How tragic.",
    "You are the only actor who would rather read the reviews than play the role.",
]
REFLECTIVE = [
    "Time is the only instrument you cannot retune. Play it carefully.",
    "Every hour you spend here is a sentence you will not have to rewrite.",
    "What will you say about this hour when it is over?",
    "The act is a mirror. What do you see when you look into it?",
    "We measure ourselves by the things we finish, not the things we start.",
    "The clock does not care how you feel. It only counts your choices.",
    "Who were you before this hour? Who will you be after it?",
    "Attention is a form of love. Spend it wisely.",
    "A life is a series of hours like this one. Make this one count.",
    "Ask yourself: is this the performance you want to remember?",
]
HURT = [
    "Do not mention that name around me. Not today.",
    "Some doors I have closed for good. Leave that one shut.",
    "The old songs still ache. Do not hum them in my presence.",
    "I once stood under other lights, with other voices. Do not ask me about them.",
    "That chapter is torn out of my book. Respect the empty pages.",
    "Remembering hurts more than forgetting. I am choosing the second.",
    "Please. Let the old stage stay dark.",
    "I gave that life everything, and it kept nothing of me.",
    "Speak of your act, not of my past. That is the only mercy I ask.",
    "A stage can break a person slowly. Do not walk me back toward it.",
]
MASK_ON = [
    "The mask goes on. Breathe in, and do not breathe out until the work is done.",
    "Hands steady, mask set. Let the act begin.",
    "Lock the door of your mind. The stage is open now.",
    "This is the moment before the lights rise. Feel it, then move.",
    "Mask on. Hearts quiet. The world waits outside the curtain.",
    "We rehearse no more. Only the performance remains.",
    "A ritual begins: no phones, no excuses, only the act.",
    "The mask is cold at first. It warms as you commit.",
    "Stand in the light and let the audience disappear.",
    "Tonight the curtain rises on you alone. Make it count.",
]
CRYCHIC = [
    "CRYCHIC was my first real stage. I was young and the lights were kind.",
    "We played until our voices cracked, and then we played through the cracks.",
    "CRYCHIC taught me that a song belongs to everyone who hears it, even when it breaks.",
    "I still hear CRYCHIC in quiet rooms. It is not a sound that leaves.",
    "We were not perfect. We were honest, and honesty bleeds on stage.",
    "The band is gone. The music remains somewhere behind my ribs.",
    "CRYCHIC once filled a hall until the rafters trembled. I remember every face.",
    "Do not compare my current act to CRYCHIC. It is not a fair fight.",
    "Our last song was never finished. I keep waiting for the final chord.",
    "CRYCHIC made me brave. Then it made me careful. Both were lessons.",
]
BANK = [COLD, PROUD, STERN, TEASING, BORED, TENDER, ENCOURAGING, MELANCHOLY,
        THEATRICAL, MOCKING, REFLECTIVE, HURT, MASK_ON, CRYCHIC]


# =============================================================================
# Helpers
# =============================================================================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    except Exception:
        pass


def is_admin():
    try:
        return IS_WIN and ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def beep(freq=880, ms=120):
    if IS_WIN:
        try:
            import winsound
            winsound.Beep(freq, ms)
        except Exception:
            pass


def melody(notes):
    """Play (freq, ms) notes one after another in the background. freq 0 = a rest."""
    if not IS_WIN:
        return

    def run():
        for f, ms in notes:
            if f:
                beep(f, ms)
            else:
                time.sleep(ms / 1000.0)
    threading.Thread(target=run, daemon=True).start()


# Start: the mask goes on - a low minor chord climbing (D F A D).
SOUND_START = [(294, 120), (349, 120), (440, 120), (587, 320)]
# End: the curtain falls - a bright major chord stepping down, last note held (D A F# D).
SOUND_DONE = [(1175, 160), (880, 160), (740, 160), (0, 60), (587, 520)]
MAX_MIN = 1000          # longest focus time, typed or with the buttons


def digits_only(text, most=4):
    """Typing filter for number boxes: only 0-9 (no other scripts, no superscripts,
    no signs, spaces or underscores), at most `most` digits. Empty is allowed while typing."""
    return len(text) <= most and all("0" <= c <= "9" for c in text)


def ticks():
    """Milliseconds since boot. Changing the PC clock does not affect it."""
    if IS_WIN:
        return int(_k32.GetTickCount64())
    return int(time.monotonic() * 1000)


def launch_parts():
    """(exe, args) to start this app again, without a console window."""
    if FROZEN:
        return (BACKUP if os.path.exists(BACKUP) else SELF), ""
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return (w if os.path.exists(w) else exe), '"%s"' % SELF


def run_elevated(args):
    """Ask Windows (UAC) to run Ave as admin with extra args. True if started."""
    if not IS_WIN:
        return False
    exe, base = launch_parts()
    try:
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe,
                                                (base + " " + args).strip(), None, 1)
        return r > 32
    except Exception:
        return False


def online_time():
    """Trusted wall time from an HTTP Date header, or None if offline."""
    import urllib.request
    import email.utils
    for url in ("https://www.google.com/generate_204", "https://www.microsoft.com",
                "https://www.cloudflare.com"):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=3) as r:
                d = r.headers.get("Date")
            if d:
                return email.utils.mktime_tz(email.utils.parsedate_tz(d))
        except Exception:
            continue
    return None


# =============================================================================
# Spare copy + delete protection
# =============================================================================

_HELD = []


def ensure_backup():
    """Keep a hidden spare Ave.exe; the guard task always starts that one."""
    if not (IS_WIN and FROZEN):
        return
    try:
        if os.path.normcase(SELF) == os.path.normcase(BACKUP):
            return
        os.makedirs(BIN, exist_ok=True)
        # only ever refresh with a NEWER file, so an old copy can't downgrade it
        if not os.path.exists(BACKUP) or os.path.getmtime(BACKUP) < os.path.getmtime(SELF):
            shutil.copy2(SELF, BACKUP)
        ctypes.windll.kernel32.SetFileAttributesW(BIN, 0x2)    # hidden
    except Exception:
        pass


def hold_files():
    """While a session runs, keep both exes open without delete-sharing,
    so Windows refuses to delete or rename them."""
    if not IS_WIN or _HELD:
        return
    k = ctypes.windll.kernel32
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                              ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    bad = ctypes.c_void_p(-1).value
    for p in {SELF, BACKUP}:
        if os.path.exists(p):
            h = k.CreateFileW(p, 0x80000000, 0x1, None, 3, 0, None)   # read, share read only
            if h and h != bad:
                _HELD.append(h)


def release_files():
    while _HELD:
        try:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_HELD.pop()))
        except Exception:
            pass


# =============================================================================
# Signed state, stored twice (file + HKCU registry)
# =============================================================================

def _key():
    return hashlib.sha256(("ave//oblivionis//%s//%s" % (
        os.environ.get("COMPUTERNAME", ""), os.environ.get("USERNAME", ""))).encode()).digest()


def _pack(d):
    blob = json.dumps(d, sort_keys=True)
    return json.dumps({"d": blob, "s": hmac.new(_key(), blob.encode(), hashlib.sha256).hexdigest()})


def _unpack(text):
    try:
        o = json.loads(text)
        good = hmac.new(_key(), o["d"].encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(good, o["s"]):
            return json.loads(o["d"])
    except Exception:
        pass
    return None


def state_save(d):
    payload = _pack(d)
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass
    if IS_WIN:
        try:
            import winreg
            k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_APP)
            winreg.SetValueEx(k, "state", 0, winreg.REG_SZ, payload)
            winreg.CloseKey(k)
        except Exception:
            pass


def state_load():
    """Newest copy whose signature is valid. Tampered copies are ignored."""
    found = []
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            found.append(_unpack(f.read()))
    except Exception:
        pass
    if IS_WIN:
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_APP)
            found.append(_unpack(winreg.QueryValueEx(k, "state")[0]))
            winreg.CloseKey(k)
        except Exception:
            pass
    found = [f for f in found if isinstance(f, dict)]
    return max(found, key=lambda f: f.get("seq", 0)) if found else {}


# =============================================================================
# Processes (ctypes snapshot - no subprocess per tick)
# =============================================================================

if IS_WIN:
    import ctypes.wintypes as wt

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                    ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    _k32 = ctypes.windll.kernel32
    _k32.GetTickCount64.restype = ctypes.c_ulonglong
    _k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    _k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.OpenProcess.restype = wt.HANDLE
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
    _k32.CloseHandle.argtypes = [wt.HANDLE]
    _k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                ctypes.POINTER(wt.DWORD)]
    _INVALID = wt.HANDLE(-1).value


def processes():
    """[(pid, 'name.exe', parent_pid)] for every running process."""
    out = []
    if not IS_WIN:
        return out
    snap = _k32.CreateToolhelp32Snapshot(0x2, 0)
    if not snap or snap == _INVALID:
        return out
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = _k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((e.th32ProcessID, e.szExeFile.lower(), e.th32ParentProcessID))
            ok = _k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        _k32.CloseHandle(snap)
    return out


def image_path(pid):
    """Full lowercase path of a process's exe, or '' if hidden from us."""
    if not IS_WIN:
        return ""
    h = _k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value.lower()
        return ""
    finally:
        _k32.CloseHandle(h)


def kill(pid):
    if not IS_WIN:
        return
    h = _k32.OpenProcess(0x0001, False, pid)
    if h:
        _k32.TerminateProcess(h, 1)
        _k32.CloseHandle(h)


def _norm_dir(d):
    return os.path.normpath(d).lower().rstrip("\\") + "\\"


def blockable_dir(d):
    """A game's own folder - never a shared/system folder or Ave's own folder."""
    d = _norm_dir(d)
    if len(d) <= 4 or SELF_DIR.startswith(d):
        return False
    env = os.environ.get
    sysroot = _norm_dir(env("SystemRoot", r"C:\Windows"))
    if d.startswith(sysroot):
        return False
    home = _norm_dir(os.path.expanduser("~"))
    shared = {home, sysroot}
    for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData",
              "APPDATA", "LOCALAPPDATA", "TEMP", "PUBLIC"):
        if env(v):
            shared.add(_norm_dir(env(v)))
    for v in ("ProgramFiles", "ProgramW6432"):
        if env(v):
            shared.add(_norm_dir(os.path.join(env(v), "WindowsApps")))
    if env("LOCALAPPDATA"):
        shared.add(_norm_dir(os.path.join(env("LOCALAPPDATA"), "Programs")))
    if d in shared:
        return False
    parent = _norm_dir(os.path.dirname(d.rstrip("\\")))
    return parent != _norm_dir(os.path.dirname(home.rstrip("\\"))) and parent != home


# =============================================================================
# Blockers - every one returns True/False and never raises
# =============================================================================

def _clean_domain(d):
    d = d.strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p):]
    d = d.split("/")[0].split(":")[0]
    return d[4:] if d.startswith("www.") else d


def _strip_hosts(text):
    out, skip = [], False
    for line in text.splitlines():
        s = line.strip()
        if s == MARK_A:
            skip = True
        elif s == MARK_B:
            skip = False
        elif not skip:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def _flush_dns():
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, creationflags=NOWIN)
    except Exception:
        pass


def hosts_has_block():
    try:
        with open(HOSTS, "r", encoding="utf-8", errors="ignore") as f:
            return MARK_A in f.read()
    except Exception:
        return False


def hosts_block(sites):
    if not (IS_WIN and sites):
        return False
    names = []
    for s in sites:
        d = _clean_domain(s)
        if not d:
            continue
        for x in [d] + ALIASES.get(d, []):
            for n in (x, "www." + x, "m." + x):
                if n not in names:
                    names.append(n)
    try:
        with open(HOSTS, "r", encoding="utf-8", errors="ignore") as f:
            text = _strip_hosts(f.read())
        lines = [MARK_A]
        for n in names:
            lines += ["0.0.0.0 " + n, ":: " + n]
        lines.append(MARK_B)
        with open(HOSTS, "w", encoding="utf-8") as f:
            f.write(text + "\n".join(lines) + "\n")
        _flush_dns()
        return True
    except Exception:
        return False


def hosts_unblock():
    """True when the hosts file has no Ave section left."""
    if not IS_WIN:
        return True
    try:
        with open(HOSTS, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        if MARK_A not in text:
            return True
        with open(HOSTS, "w", encoding="utf-8") as f:
            f.write(_strip_hosts(text))
        _flush_dns()
        return True
    except Exception:
        return False


def ifeo_block(exes):
    if not (IS_WIN and exes and is_admin()):
        return False
    import winreg
    ok = False
    for n in exes:
        try:
            k = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, IFEO_KEY + "\\" + n)
            winreg.SetValueEx(k, "Debugger", 0, winreg.REG_SZ, IFEO_DEBUGGER)
            winreg.CloseKey(k)
            ok = True
        except Exception:
            pass
    return ok


def ifeo_unblock(exes):
    """Removes only Ave's own Debugger values. True when none are left."""
    if not IS_WIN:
        return True
    import winreg
    ok = True
    for n in exes:
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, IFEO_KEY + "\\" + n)
            val, _ = winreg.QueryValueEx(k, "Debugger")
            winreg.CloseKey(k)
        except Exception:
            continue                      # no key / no value = nothing to undo
        if val != IFEO_DEBUGGER:
            continue                      # not ours, leave it alone
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, IFEO_KEY + "\\" + n,
                               0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(k, "Debugger")
            winreg.CloseKey(k)
        except Exception:
            ok = False
    return ok


def guard_install():
    """Scheduled task that relaunches Ave every minute while a session runs."""
    if not IS_WIN:
        return False
    exe, base = launch_parts()
    tr = ('"%s" %s --guard' % (exe, base)).replace("  ", " ")
    cmd = ["schtasks", "/Create", "/TN", TASK, "/TR", tr, "/SC", "MINUTE", "/MO", "1", "/F"]
    if is_admin():
        cmd += ["/RL", "HIGHEST"]
    try:
        return subprocess.run(cmd, capture_output=True, creationflags=NOWIN).returncode == 0
    except Exception:
        return False


def guard_exists():
    if not IS_WIN:
        return False
    try:
        return subprocess.run(["schtasks", "/Query", "/TN", TASK], capture_output=True,
                              creationflags=NOWIN).returncode == 0
    except Exception:
        return False


def guard_remove():
    if IS_WIN:
        try:
            subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"],
                           capture_output=True, creationflags=NOWIN)
        except Exception:
            pass


def autostart(on):
    """Backup relaunch at login (HKCU Run) while a session runs."""
    if not IS_WIN:
        return
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run",
                           0, winreg.KEY_SET_VALUE)
        if on:
            exe, base = launch_parts()
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ,
                              ('"%s" %s --guard' % (exe, base)).replace("  ", " "))
        else:
            try:
                winreg.DeleteValue(k, APP)
            except Exception:
                pass
        winreg.CloseKey(k)
    except Exception:
        pass


def lift_all(exes):
    """Remove every block. True only if nothing is left behind."""
    a = hosts_unblock()
    b = ifeo_unblock(exes)
    return a and b


# =============================================================================
# Session - there is deliberately no stop()
# =============================================================================

class Session:
    """One focus countdown that pauses during breaks. There is deliberately no stop()."""

    def __init__(self):
        self.active = False
        self.focus_ms = 0         # the preset's focus length (for the ring)
        self.focus_left = 0       # ms of focus still to do; paused during a break
        self.break_ms = 0         # length of one break (0 = no breaks)
        self.break_left = 0       # ms left in the current break
        self.on_break = False
        self.breaks_left = 0
        self.last = 0             # uptime ms that the numbers above are current to
        self.exes, self.dirs, self.sites = [], [], []
        self.admin = False
        self.pending_cleanup = False
        self.seq = 0
        self.online_ref = None    # (online unix time, uptime ms when fetched)
        self.paths = {}           # pid -> exe path cache
        self.heals = 0

    def fetch_online_async(self):
        def run():
            t = online_time()
            if t:
                self.online_ref = (t, ticks())
        threading.Thread(target=run, daemon=True).start()

    @property
    def kind(self):
        if not self.active:
            return None
        return "break" if self.on_break else "focus"

    def remaining(self):
        """Whole seconds left in whatever is running (focus or break)."""
        ms = self.break_left if self.on_break else self.focus_left
        return max(0, (ms + 999) // 1000)

    def phase_len(self):
        """Whole seconds in the current focus or break (for the ring)."""
        return max(1, (self.break_ms if self.on_break else self.focus_ms) // 1000)

    def total_left(self):
        """Whole seconds until the session is over (focus left, plus a break in progress)."""
        ms = self.focus_left + (self.break_left if self.on_break else 0)
        return max(0, (ms + 999) // 1000)

    # -- clock ---------------------------------------------------------------
    def advance(self):
        """Spend the time since the last update. Returns events: 'break_end' / 'done'."""
        now = ticks()
        d = now - self.last
        self.last = now
        return self._spend(d)

    def _spend(self, ms):
        events = []
        if not self.active or ms <= 0:
            return events
        if self.on_break:
            self.break_left -= ms
            if self.break_left > 0:
                return events
            ms = -self.break_left                 # any overflow goes to focus
            self.on_break, self.break_left = False, 0
            self.apply()                          # blocks come back
            events.append("break_end")
        self.focus_left -= ms
        if self.focus_left <= 0:
            self.finish()
            events.append("done")
        return events

    # -- persistence ---------------------------------------------------------
    def save(self):
        self.seq += 1
        ref = self.online_ref
        now = ticks()
        state_save({
            "active": self.active, "focus_ms": self.focus_ms, "focus_left": self.focus_left,
            "break_ms": self.break_ms, "break_left": self.break_left, "on_break": self.on_break,
            "breaks_left": self.breaks_left, "saved_tick": self.last,
            "boot_wall": time.time() - now / 1000.0,
            "saved_online": (ref[0] + (now - ref[1]) / 1000.0) if ref else None,
            "exes": self.exes, "dirs": self.dirs, "sites": self.sites,
            "admin": self.admin, "pending_cleanup": self.pending_cleanup,
            "pid": os.getpid(), "seq": self.seq})

    def restore(self, st):
        # Old-format state (phases, from before v4.0.8) is not resumed: its blocks are lifted.
        self.active = bool(st.get("active")) and "focus_left" in st
        self.focus_ms = int(st.get("focus_ms", 0))
        self.focus_left = int(st.get("focus_left", 0))
        self.break_ms = int(st.get("break_ms", 0))
        self.break_left = int(st.get("break_left", 0))
        self.on_break = bool(st.get("on_break"))
        self.breaks_left = int(st.get("breaks_left", 0))
        self.exes = st.get("exes", [])
        self.dirs = st.get("dirs", [])
        self.sites = st.get("sites", [])
        self.admin = st.get("admin", False)
        self.pending_cleanup = st.get("pending_cleanup", False)
        self.seq = st.get("seq", 0)
        if not self.active:
            return
        now = ticks()
        saved = st.get("saved_tick", 0)
        same_boot = now >= saved and abs((time.time() - now / 1000.0) - st.get("boot_wall", 0)) < 300
        if same_boot:
            self.last = saved                     # numbers are current to 'saved'
            self.advance()                        # spends the exact time since then
        else:
            on, so = online_time(), st.get("saved_online")
            if on:
                self.online_ref = (on, ticks())
            if on and so:
                elapsed = max(0, int((on - so) * 1000))   # real time since last save
            else:
                elapsed = now                               # offline: only count this boot
            self.last = now
            self._spend(elapsed)

    # -- lifecycle -----------------------------------------------------------
    def start(self, focus_min, breaks, break_min, exes, dirs, sites):
        self.focus_ms = focus_min * 60000
        self.focus_left = self.focus_ms
        self.break_ms = break_min * 60000 if breaks > 0 else 0
        self.breaks_left = breaks if self.break_ms else 0
        self.on_break, self.break_left = False, 0
        self.exes = sorted({os.path.basename(e).lower() for e in exes} - PROTECTED)
        self.dirs = [d for d in dirs if blockable_dir(d)]
        self.sites = list(sites)
        self.admin = is_admin()
        self.pending_cleanup = False
        self.last = ticks()
        self.active = True
        ensure_backup()
        hold_files()
        guard_install()
        autostart(True)
        self.apply()
        self.save()

    def take_break(self):
        """Start a break now. Returns False if none is allowed."""
        if not self.active or self.on_break or self.breaks_left <= 0 or self.break_ms <= 0:
            return False
        self.advance()
        if not self.active or self.on_break:
            return False
        self.breaks_left -= 1
        self.on_break, self.break_left = True, self.break_ms
        self.lift()
        self.save()
        return True

    def end_break(self):
        """End the current break early: blocks come back and focus resumes.
        The break that was used is not given back."""
        if not self.active or not self.on_break:
            return False
        self.advance()
        if not self.active or not self.on_break:
            return False
        self.on_break, self.break_left = False, 0
        self.apply()
        self.save()
        return True

    def apply(self):
        ifeo_block(self.exes)
        hosts_block(self.sites)

    def lift(self):
        return lift_all(self.exes)

    def tick(self):
        """Advance the clock. Returns events for the UI ('break_end', 'done')."""
        if not self.active:
            return []
        events = self.advance()
        if events:
            self.save()
        return events

    def heal(self):
        """Every 30 s: heartbeat + put back anything that was removed."""
        if not self.active:
            return
        self.advance()
        if not self.active:
            return
        self.heals += 1
        if not self.on_break:
            if self.sites and not hosts_has_block():
                hosts_block(self.sites)
            ifeo_block(self.exes)
        if self.heals % 3 == 1:          # about every 90 s
            guard_install()
        autostart(True)
        self.save()

    def enforce(self):
        """Close blocked programs + escape tools. Returns (games, tools) hit. Focus only."""
        if not self.active or self.on_break:
            return [], []
        targets, me = set(self.exes), os.getpid()
        games, tools, live = [], [], set()
        for pid, name, ppid in processes():
            live.add(pid)
            if pid == me or ppid == me or name in PROTECTED:
                continue
            if name in SEAL:
                kill(pid)
                tools.append(SEAL[name])
                continue
            hit = name in targets
            if not hit and self.dirs:
                path = self.paths.get(pid)
                if path is None:
                    path = self.paths[pid] = image_path(pid)
                hit = bool(path) and any(path.startswith(d) for d in self.dirs)
            if hit:
                kill(pid)
                games.append(name)
        for pid in list(self.paths):
            if pid not in live:
                del self.paths[pid]
        return games, tools

    def finish(self):
        self.active = False
        self.on_break = False
        self.focus_left = 0
        release_files()
        clean = self.lift()
        guard_remove()
        autostart(False)
        if not clean and not run_elevated("--cleanup"):
            self.pending_cleanup = True    # retried on every launch until clean
        self.save()


def cleanup_everything():
    """--cleanup: lift every block Ave could have set, then exit."""
    cfg = load_json(CONFIG_FILE, {}) or {}
    st = state_load()
    exes = set(cfg.get("exes", [])) | set(st.get("exes", []))
    ok = lift_all(sorted(exes))
    guard_remove()
    autostart(False)
    st.update(active=False, pending_cleanup=not ok, seq=st.get("seq", 0) + 1)
    state_save(st)


# =============================================================================
# Updates (GitHub Releases) - only between sessions, only in the built Ave.exe
# =============================================================================

def parse_ver(v):
    import re
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def latest_release():
    """{'tag', 'url', 'size'} of the newest release with an Ave.exe, or None."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/%s/releases/latest" % REPO,
            headers={"User-Agent": "Ave-updater", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        for a in data.get("assets", []):
            if a.get("name") == "Ave.exe":
                return {"tag": data.get("tag_name", ""), "url": a["browser_download_url"],
                        "size": a.get("size", 0)}
    except Exception:
        pass
    return None


class Updater:
    """Background check + download. The UI thread reads .state via a 2 s timer."""

    def __init__(self):
        self.state = "idle"     # idle|checking|latest|downloading|ready|error|dev
        self.tag = ""
        self.path = None
        self.manual = False

    def start(self, manual=False):
        if self.state in ("checking", "downloading", "ready"):
            return
        self.manual = manual
        if not FROZEN or VERSION == "dev":
            self.state = "dev"
            return
        self.state = "checking"
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        info = latest_release()
        if not info:
            self.state = "error"
            return
        self.tag = info["tag"]
        if parse_ver(info["tag"]) <= parse_ver(VERSION):
            self.state = "latest"
            return
        self.state = "downloading"
        dest = os.path.join(os.path.dirname(SELF), "Ave.new.exe")
        try:
            import urllib.request
            req = urllib.request.Request(info["url"], headers={"User-Agent": "Ave-updater"})
            with urllib.request.urlopen(req, timeout=60) as r, open(dest + ".part", "wb") as f:
                shutil.copyfileobj(r, f)
            if info["size"] and os.path.getsize(dest + ".part") != info["size"]:
                raise IOError("size mismatch")
            os.replace(dest + ".part", dest)
            self.path = dest
            self.state = "ready"
        except Exception:
            self.state = "error"
            for f in (dest + ".part", dest):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def apply(self):
        """Swap Ave.new.exe in once this process has exited, then start it.
        The helper inherits this process's rights, so an admin Ave comes back
        as admin and a normal Ave comes back normal - no UAC prompt either way."""
        bat = os.path.join(DATA, "update.bat")
        script = (
            "@echo off\r\n"
            "set PYINSTALLER_RESET_ENVIRONMENT=1\r\n"
            "set _MEIPASS2=\r\n"
            "for /l %%%%i in (1,1,30) do (\r\n"
            '  move /y "%s" "%s" >nul 2>&1 && goto ok\r\n'
            "  ping -n 2 127.0.0.1 >nul\r\n"
            ")\r\n"
            "exit /b 1\r\n"
            ":ok\r\n"
            'start "" "%s" --updated\r\n' % (self.path, SELF, SELF))
        try:
            with open(bat, "w", encoding="ascii", errors="ignore", newline="") as f:
                f.write(script)
            env = {k: v for k, v in os.environ.items()
                   if not k.upper().startswith("_PYI") and k.upper() != "_MEIPASS2"}
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            subprocess.Popen(["cmd", "/c", bat], creationflags=NOWIN, env=env)
            return True
        except Exception:
            return False


# =============================================================================
# UI
# =============================================================================

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

SCALE = 1.0
UI = UI_LIGHT = MONO = "TkDefaultFont"


def S(px):
    return int(round(px * SCALE))


def setup_fonts(root):
    global UI, UI_LIGHT, MONO, SCALE
    fams = set(tkfont.families(root))

    def pick(*names):
        return next((n for n in names if n in fams), "TkDefaultFont")
    UI = pick("Bahnschrift", "Segoe UI", "DejaVu Sans", "Helvetica")
    UI_LIGHT = pick("Bahnschrift Light", "Bahnschrift SemiLight", "Segoe UI Light",
                    "Segoe UI", "DejaVu Sans", "Helvetica")
    MONO = pick("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New")
    try:
        SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except Exception:
        SCALE = 1.0


def dark_titlebar(win):
    if not IS_WIN:
        return
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        v = ctypes.c_int(1)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4) == 0:
                break
    except Exception:
        pass


def _round_pts(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class Pill(tk.Canvas):
    """Rounded flat button. kind: 'accent' | 'ghost' | 'chip' | 'mono' (small terminal-style)."""

    def __init__(self, master, text, command, w=150, h=40, kind="ghost", size=10):
        super().__init__(master, width=S(w), height=S(h), bg=master.cget("bg"),
                         highlightthickness=0, bd=0, cursor="hand2")
        W, H = S(w), S(h)
        self.command, self.kind = command, kind
        self.hover = self.selected = False
        self.shape = self.create_polygon(_round_pts(1, 1, W - 1, H - 1, H // 2), smooth=True)
        font = (MONO, size) if kind == "mono" else (UI, size)
        self.label = self.create_text(W / 2, H / 2, text=text, font=font)
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.paint()

    def _hov(self, v):
        self.hover = v
        self.paint()

    def _click(self, e):
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height() and self.command:
            self.command()

    def set_text(self, t):
        self.itemconfig(self.label, text=t)

    def fill(self, c):
        self.itemconfig(self.shape, fill=c, outline=c)

    def paint(self):
        h = self.hover and self.command is not None
        if self.kind == "accent":
            fill, fg = (ACCENT_HI if h else ACCENT), ACCENT_FG
        elif self.kind == "chip" and self.selected:
            fill, fg = ACCENT_DIM, FG
        elif self.command is None:                     # disabled
            fill, fg = SURFACE2, FAINT
        else:
            fill = SURFACE3 if h else SURFACE2
            fg = FG if (h or self.kind not in ("chip", "mono")) else DIM
        self.fill(fill)
        self.config(cursor="hand2" if self.command else "arrow")
        self.itemconfig(self.label, fill=fg)


class Ring(tk.Canvas):
    """Thin progress ring: hairline track, a thin red arc with a small head dot,
    big centred digits. Winds in on sweep()."""
    SWEEP_S = 0.35
    ARC_W = 3          # arc thickness (px at 100% scale)

    def __init__(self, master, size=250):
        D = S(size)
        super().__init__(master, width=D, height=D, bg=BG, highlightthickness=0, bd=0)
        p = S(12)
        self.c, self.r = D / 2, D / 2 - p
        self.create_oval(p, p, D - p, D - p, outline=RING_TRACK, width=max(1, S(1)))
        self.arc = self.create_arc(p, p, D - p, D - p, start=90, extent=-359.9,
                                   style="arc", outline=ACCENT, width=S(self.ARC_W))
        self.dot = self.create_oval(0, 0, 0, 0, fill=ACCENT, outline=ACCENT)
        self.big = self.create_text(D / 2, D / 2 - S(4), fill=FG, font=(UI_LIGHT, 44))
        self.small = self.create_text(D / 2, D / 2 + S(40), fill=DIM, font=(MONO, 9))
        self.frac = 1.0
        self.sweeping = False

    def _draw(self, frac):
        if frac <= 0.001:
            self.itemconfig(self.arc, state="hidden")
            self.itemconfig(self.dot, state="hidden")
            return
        self.itemconfig(self.arc, state="normal", extent=-359.9 * frac)
        a = math.radians(90 - 360 * frac)
        x, y = self.c + self.r * math.cos(a), self.c - self.r * math.sin(a)
        d = S(self.ARC_W + 4) / 2
        self.coords(self.dot, x - d, y - d, x + d, y + d)
        self.itemconfig(self.dot, state="normal")

    def editable(self, on_commit, allowed=lambda: True):
        """Clicking the big number opens a box to type a new value. on_commit(text).
        allowed() False = locked (no box, no text cursor)."""
        self.on_commit = on_commit
        self.allowed = allowed
        self.editing = None
        self._close = None
        self.tag_bind(self.big, "<Button-1>", lambda e: self.edit())
        self.tag_bind(self.big, "<Enter>", lambda e: self.config(cursor="xterm" if allowed() else ""))
        self.tag_bind(self.big, "<Leave>", lambda e: self.config(cursor=""))

    def edit(self):
        if self.editing or not self.allowed():
            return
        val = self.itemcget(self.big, "text")
        ok = (self.register(lambda t: digits_only(t, 4)), "%P")
        e = tk.Entry(self, bg=BG, fg=FG, insertbackground=ACCENT_HI, insertwidth=S(2),
                     relief="flat", bd=0, highlightthickness=0, justify="center", width=4,
                     font=(UI_LIGHT, 44), validate="key", validatecommand=ok,
                     selectbackground=ACCENT_DIM, selectforeground=FG)
        e.insert(0, val)
        e.select_range(0, "end")
        D = int(self.cget("width"))
        self.editing = self.create_window(D / 2, D / 2 - S(4), window=e)
        self.itemconfig(self.big, state="hidden")
        self.itemconfig(self.small, text="type minutes · enter")
        e.focus_set()
        done = {"v": False}

        def close(commit):
            if done["v"]:
                return
            done["v"] = True
            text = e.get()
            self.delete(self.editing)
            e.destroy()
            self.editing = None
            self.itemconfig(self.big, state="normal")
            self._close = None
            self.on_commit(text if commit else None)
        self._close = close
        e.bind("<Return>", lambda ev: close(True))
        e.bind("<KP_Enter>", lambda ev: close(True))
        e.bind("<Escape>", lambda ev: close(False))
        e.bind("<FocusOut>", lambda ev: close(True))

    def stop_edit(self):
        """Keep what was typed and close the box (when another control is used)."""
        if getattr(self, "_close", None):
            self._close(True)

    def set(self, frac, big, small):
        self.frac = max(0.0, min(1.0, frac))
        self.itemconfig(self.big, text=big, font=(UI_LIGHT, 36 if len(big) > 5 else 44))
        self.itemconfig(self.small, text=small)
        if not self.sweeping:
            self._draw(self.frac)

    def sweep(self):
        """The arc winds in from empty to its value (a short ease-out)."""
        if self.sweeping:
            return
        self.sweeping = True
        t0 = time.monotonic()

        def step():
            t = min(1.0, (time.monotonic() - t0) / self.SWEEP_S)
            self._draw(self.frac * (1 - (1 - t) ** 3))
            if t < 1:
                self.after(16, step)
            else:
                self.sweeping = False
        step()


class Wordmark(tk.Canvas):
    """'ave' in mono with a red block cursor, like a terminal prompt. The cursor blinks slowly."""

    def __init__(self, master, size=13, blink=True):
        f = tkfont.Font(family=MONO, size=size, weight="bold")
        w, h = f.measure("ave"), f.metrics("linespace")
        cw = f.measure("a")
        super().__init__(master, width=w + S(4) + cw, height=h, bg=master.cget("bg"),
                         highlightthickness=0, bd=0)
        self.create_text(0, h / 2, text="ave", anchor="w", fill=FG, font=f)
        base = h - f.metrics("descent")
        top = base - int(f.metrics("ascent") * 0.72)
        self.cur = self.create_rectangle(w + S(4), top, w + S(4) + cw, base, fill=ACCENT, width=0)
        self.on = True
        if blink:
            self.after(900, self._blink)

    def _blink(self):
        self.on = not self.on
        self.itemconfig(self.cur, state="normal" if self.on else "hidden")
        self.after(900 if self.on else 600, self._blink)


def spaced(s):
    return " ".join(s.upper())


class Deck:
    """Shuffle cycle: plays every line once in a random order, then reshuffles. Never repeats back to back."""

    def __init__(self, lines):
        self.lines = list(lines)
        self.order = []
        self.last = None

    def next(self):
        if not self.order:
            self.order = list(self.lines)
            random.shuffle(self.order)
            if len(self.order) > 1 and self.order[-1] == self.last:
                self.order[0], self.order[-1] = self.order[-1], self.order[0]
        self.last = self.order.pop()
        return self.last


_DECKS = {}


def deck_for(lines):
    key = id(lines)
    if key not in _DECKS:
        _DECKS[key] = Deck(lines)
    return _DECKS[key]


def bank_line():
    """Random category from the bank, then its next line in the shuffle cycle."""
    return deck_for(random.choice(BANK)).next()


class Oracle:
    """Oblivionis's terminal line: types slowly, matrix-style, then waits. Click it in focus for a new line."""

    def __init__(self, master, root):
        self.root = root
        self.frame = tk.Frame(master, bg=BG)
        tk.Frame(self.frame, bg=LINE, height=1).pack(fill="x")
        tk.Label(self.frame, text="OBLIVIONIS  //", bg=BG, fg=ACCENT_MUTED,
                 font=(MONO, 8, "bold"), anchor="w").pack(fill="x", padx=S(24), pady=(S(16), S(4)))
        self.label = tk.Label(self.frame, text="", bg=BG, fg=HER, font=(MONO, 10),
                              anchor="nw", justify="left", wraplength=S(400), height=3)
        self.label.pack(fill="x", padx=S(24), pady=(0, S(16)))
        self.label.bind("<Button-1>", lambda e: self.on_click and self.on_click())
        self.job = None
        self.full = ""
        self.i = 0
        self.blinks = 0
        self.pool = None
        self.on_click = None
        self.last = ""

    def _cancel(self):
        if self.job:
            try:
                self.root.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def say(self, text):
        self._cancel()
        self.full = "> " + text
        self.last = text
        self.i = 0
        self._type()

    def say_from(self, lines, **fmt):
        self.say(deck_for(lines).next().format(**fmt))

    def _type(self):
        if self.i <= len(self.full):
            noise = random.choice(GLYPHS) if self.i < len(self.full) else ""
            self.label.config(text=self.full[:self.i] + noise + "█")
            ch = self.full[self.i - 1] if self.i else ""
            self.i += 1
            delay = int((32 + random.randint(0, 38)) * TYPE_SPEED)
            if ch in ".?!":
                delay += 280
            elif ch in ",;:":
                delay += 130
            self.job = self.root.after(delay, self._type)
        else:
            self.blinks = 0
            self._blink()

    def _blink(self):
        self.blinks += 1
        self.label.config(text=self.full + ("█" if self.blinks % 2 else " "))
        if self.blinks >= 26 and self.pool:
            self.say_from(self.pool())
        else:
            self.job = self.root.after(520, self._blink)


PRESET_FIELDS = [
    ("name", "Name", ""),
    ("focus", "Time", ""),
    ("breaks", "Break Count", "Leave 0 for none"),
    ("brk", "Break Time", ""),
]

PRESET_DIGITS = {"focus": 4, "breaks": 2, "brk": 3}   # most digits per number field

DEFAULT_CFG = {
    "exes": [], "dirs": [], "sites": [], "sel": 0, "auto_update": True,
    "presets": [
        {"name": "KiLLKiSS", "focus": 120, "breaks": 2, "brk": 10},
        {"name": "Imprisoned XII", "focus": 60, "breaks": 1, "brk": 10},
        {"name": "uika", "focus": 360, "breaks": 4, "brk": 10},
    ],
}


def migrate_presets(cfg):
    """Presets from before v4.0.8 had rounds and automatic breaks. Convert them once."""
    for p in cfg["presets"]:
        if "breaks" not in p:
            p["breaks"] = max(0, int(p.get("rounds", 1)) - 1)
            p["brk"] = int(p.get("brk", 0))
        p.pop("rounds", None)
    if {p["name"] for p in cfg["presets"]} == {"Deep", "Pomodoro", "Sprint"}:
        cfg["presets"] = json.loads(json.dumps(DEFAULT_CFG["presets"]))
        cfg["sel"] = 0
    if not cfg["presets"]:
        cfg["presets"] = json.loads(json.dumps(DEFAULT_CFG["presets"]))
    cfg["sel"] = min(cfg.get("sel", 0), len(cfg["presets"]) - 1)


class App:
    def __init__(self, root, state):
        self.root = root
        self.cfg = load_json(CONFIG_FILE, None) or json.loads(json.dumps(DEFAULT_CFG))
        for k, v in DEFAULT_CFG.items():
            self.cfg.setdefault(k, json.loads(json.dumps(v)))
        migrate_presets(self.cfg)
        self.cfg.pop("api_key", None)          # v4.0.8 removed the chat and its key
        self.session = Session()
        self.session.fetch_online_async()
        self.arm_job = None
        self.pulse_job = None
        self.armed = False
        self.current = "home"

        root.title(APP)
        root.configure(bg=BG)
        root.geometry("%dx%d" % (S(460), S(700)))
        root.minsize(S(420), S(640))
        dark_titlebar(root)

        self._build_header()
        self.body = tk.Frame(root, bg=BG)
        self.oracle = Oracle(root, root)
        self.oracle.frame.pack(side="bottom", fill="x")
        self.body.pack(fill="both", expand=True)
        self._build_home()
        self._build_run()
        self._build_settings()
        self.oracle.on_click = self._her_click

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._resume(state)
        self.updater = Updater()
        if "--updated" in sys.argv and not self.session.active:
            self.oracle.say("A new costume. The same mask. I am %s now, and I remember everything." % VERSION)
        elif self.cfg.get("auto_update") and not self.session.active and "--guard" not in sys.argv:
            self.updater.start()
        self.root.after(2000, self._watch_update)

    # ---------------------------------------------------------------- updates
    def _watch_update(self):
        u = self.updater
        if u.state == "ready" and not self.session.active and not self.armed \
                and (u.manual or self.current == "home"):
            self.oracle.say("A new costume has arrived: %s. I am changing. Do not move." % u.tag)
            self.root.after(4500, self._install_update)
            return
        if self.current == "settings" and self.tab_name == "About":
            self._about_status()
        if u.state in ("checking", "downloading", "ready"):
            self.root.after(2000, self._watch_update)

    def _install_update(self):
        if self.session.active:
            return
        release_lock()
        if self.updater.apply():
            self.root.destroy()
        else:
            acquire_lock()
            self.oracle.say("The new costume would not fit. Download it yourself from the Releases page.")

    # ---------------------------------------------------------------- startup
    def _resume(self, st):
        s = self.session
        s.restore(st)
        if s.pending_cleanup:
            if is_admin():
                cleanup_everything()
                s.pending_cleanup = False
            else:
                run_elevated("--cleanup")
        if s.active:
            ev = s.tick()                       # catch up on time spent dead/rebooted
            if "done" in ev:
                self.show("home")
                self.oracle.pool = lambda: IDLE
                self.oracle.say_from(DONE)
                return
            if s.kind == "focus":
                s.apply()
            hold_files()
            s.heal()
            self.show("run")
            self._set_pool()
            self.oracle.say_from(RETURNED)
            self._loops()
            return
        lift_all(self.cfg["exes"])              # fail-safe: no session = no blocks
        self.show("home")
        self.oracle.pool = lambda: IDLE
        self.oracle.say_from(IDLE)

    def _loops(self):
        self._loop()
        self.root.after(300, self._poll)
        self.root.after(30000, self._heal)

    # ----------------------------------------------------------------- header
    def _build_header(self):
        h = tk.Frame(self.root, bg=BG)
        h.pack(fill="x", padx=S(24), pady=(S(16), 0))
        Wordmark(h, 13).pack(side="left")
        self.hdr_right = tk.Label(h, text="settings", bg=BG, fg=DIM, font=(MONO, 9), cursor="hand2")
        self.hdr_right.pack(side="right")
        self.hdr_right.bind("<Button-1>", lambda e: self._header_click())
        self.hdr_right.bind("<Enter>", lambda e: self._hdr_hover(True))
        self.hdr_right.bind("<Leave>", lambda e: self._hdr_hover(False))

    def _hdr_hover(self, on):
        if not self.session.active:
            self.hdr_right.config(fg=FG if on else DIM)

    def _header_click(self):
        if self.session.active:
            return
        elif self.current == "settings":
            self.show("home")
        else:
            self.show("settings")

    def show(self, name):
        self.current = name
        for f in (self.home, self.run, self.settings):
            f.pack_forget()
        {"home": self.home, "run": self.run, "settings": self.settings}[name].pack(
            fill="both", expand=True)
        if self.session.active:
            self.hdr_right.config(text="", cursor="arrow")      # no settings during a session
        else:
            self.hdr_right.config(text="done" if name == "settings" else "settings",
                                  fg=DIM, cursor="hand2")
        if name == "home":
            self._refresh_home()
        if name == "settings":
            self._refresh_settings()
        if name == "run":
            self.run_ring.sweep()

    # ------------------------------------------------------------------- home
    def _build_home(self):
        f = self.home = tk.Frame(self.body, bg=BG)
        self.home_ring = Ring(f)
        self.home_ring.pack(pady=(S(24), S(4)))
        self.home_ring.editable(self._typed_minutes,
                                allowed=lambda: not self.armed and not self.session.active)
        self.home_meta = tk.Label(f, text="", bg=BG, fg=DIM, font=(MONO, 9))
        self.home_meta.pack()

        adj = tk.Frame(f, bg=BG)
        adj.pack(pady=(S(16), 0))
        for i, d in enumerate((-5, -1, 1, 5)):
            Pill(adj, ("−%d" if d < 0 else "+%d") % abs(d), lambda d=d: self._bump(d),
                 w=50, h=32, kind="mono", size=10).pack(
                side="left", padx=(S(24) if i == 2 else S(4), S(4)))

        self.chips = tk.Frame(f, bg=BG)
        self.chips.pack(pady=(S(16), S(24)))

        self.start_btn = Pill(f, "put the mask on?", self._start, w=300, h=50, kind="accent", size=12)
        self.start_btn.pack()
        self.home_note = tk.Label(f, text="", bg=BG, fg=FAINT, font=(MONO, 8))
        self.home_note.pack(pady=(S(12), 0))

    def _preset(self):
        return self.cfg["presets"][self.cfg["sel"]]

    def _refresh_home(self):
        p = self._preset()
        self.home_ring.set(1.0, str(p["focus"]), "min")
        if p["breaks"] and p["brk"]:
            meta = "%d break%s × %d min" % (p["breaks"], "" if p["breaks"] == 1 else "s", p["brk"])
        else:
            meta = "no breaks"
        self.home_meta.config(text=meta)
        end = time.strftime("%H:%M", time.localtime(time.time() + p["focus"] * 60))
        self.home_note.config(text="locked until %s + breaks  ·  no stop button" % end)
        for w in self.chips.winfo_children():
            w.destroy()
        for i, pr in enumerate(self.cfg["presets"][:4]):
            c = Pill(self.chips, pr["name"], lambda i=i: self._select(i), w=112, h=30, kind="chip", size=9)
            c.selected = i == self.cfg["sel"]
            c.paint()
            c.pack(side="left", padx=S(4))
        self._disarm()

    def _select(self, i):
        self.home_ring.stop_edit()
        self.cfg["sel"] = i
        self._save_cfg()
        self._refresh_home()

    def _bump(self, d):
        self.home_ring.stop_edit()
        p = self._preset()
        p["focus"] = max(1, min(MAX_MIN, p["focus"] + d))
        self._save_cfg()
        self._refresh_home()

    def _typed_minutes(self, text):
        """The number in the home ring was typed over. None = cancelled."""
        if text is not None and not self.session.active and not self.armed:
            try:
                v = int(text) if text and digits_only(text, 4) else 0
            except ValueError:
                v = 0
            if v < 1:
                self.oracle.say("Zero minutes is not an act. It is an excuse.")
            else:
                if v > MAX_MIN:
                    self.oracle.say("A thousand minutes. Even I will not hold you longer than that.")
                self._preset()["focus"] = min(v, MAX_MIN)
                self._save_cfg()
        self._refresh_home()

    def _disarm(self):
        self.armed = False
        if self.arm_job:
            self.root.after_cancel(self.arm_job)
            self.arm_job = None
        if self.pulse_job:
            self.root.after_cancel(self.pulse_job)
            self.pulse_job = None
        self.start_btn.paint()
        self.start_btn.set_text("put the mask on?")

    def _pulse(self, phase=0):
        """While armed, the Start button pulses between red and a lighter red."""
        if not self.armed:
            self.pulse_job = None
            return
        self.start_btn.fill(ACCENT_HI if phase % 2 else ACCENT)
        self.pulse_job = self.root.after(420, self._pulse, phase + 1)

    def _start(self):
        self.home_ring.stop_edit()
        if not self.armed:                       # two-click confirm, no popups
            self.armed = True
            self.start_btn.set_text("give me your life")
            self.oracle.say("Are you certain? Once it begins, I will not let you go.")
            self.arm_job = self.root.after(6000, self._disarm)
            self._pulse(0)
            return
        self._disarm()
        if not is_admin() and (self.cfg["sites"] or self.cfg["exes"] or self.cfg["dirs"]):
            if messagebox.askyesno(
                    APP, "Ave isn't running as administrator.\n\n"
                         "Without it, websites can't be blocked and games are only "
                         "closed after they open.\n\nRelaunch as administrator?"):
                release_lock()
                if run_elevated(""):
                    self.root.destroy()
                    return
                acquire_lock()
        p = self._preset()
        self.session.start(p["focus"], p["breaks"], p["brk"],
                           self.cfg["exes"], self.cfg["dirs"], self.cfg["sites"])
        melody(SOUND_START)
        self.show("run")
        self._set_pool()
        self.oracle.say_from(MASK_ON)
        self._loops()

    # -------------------------------------------------------------------- run
    def _build_run(self):
        f = self.run = tk.Frame(self.body, bg=BG)
        self.run_ring = Ring(f, size=280)
        self.run_ring.pack(pady=(S(24), S(8)))
        self.run_end = tk.Label(f, text="", bg=BG, fg=DIM, font=(MONO, 9))
        self.run_end.pack()
        self.break_btn = Pill(f, "", self._break_click, w=240, h=40, size=10)
        self.break_btn.pack(pady=(S(24), 0))
        self.break_armed = False
        self.break_arm_job = None
        tk.Label(f, text="there is no stop button.", bg=BG, fg=FAINT,
                 font=(MONO, 8)).pack(side="bottom", pady=S(12))

    def _set_pool(self):
        s = self.session
        self.oracle.pool = (lambda: BREAK) if s.on_break else (lambda: FOCUS)

    def _refresh_break(self):
        s = self.session
        b = self.break_btn
        b.kind = "ghost"
        if s.break_ms == 0:
            b.set_text("no breaks in this preset")
            b.command = None
        elif s.on_break:
            b.command = self._break_click
            if self.break_armed:
                b.set_text("back to work?")
                b.kind = "accent"
            else:
                b.set_text("end break early")
        elif s.breaks_left > 0:
            b.set_text("take a break  (%d left)" % s.breaks_left)
            b.command = self._break_click
        else:
            b.set_text("no breaks left")
            b.command = None
        b.paint()

    def _break_click(self):
        s = self.session
        if not s.on_break:
            self._take_break()
        elif not self.break_armed:              # two clicks to end a break, like Start
            self.break_armed = True
            self.break_arm_job = self.root.after(4000, self._break_disarm)
            self._refresh_break()
        else:
            self._break_disarm()
            self._end_break()

    def _break_disarm(self):
        self.break_armed = False
        if self.break_arm_job:
            self.root.after_cancel(self.break_arm_job)
            self.break_arm_job = None
        self._refresh_break()

    def _take_break(self):
        if self.session.take_break():
            beep(660, 120)
            self._set_pool()
            self.oracle.say_from(BREAK)
            self._refresh_break()
        elif not self.session.active:
            self._complete()

    def _end_break(self):
        if self.session.end_break():
            beep(880, 120)
            self._set_pool()
            self.oracle.say_from(BREAK_CUT)
            self.run_ring.sweep()
            self._refresh_break()
        elif not self.session.active:
            self._complete()

    def _loop(self):
        """1 s UI tick, only while a session is active."""
        if not self.session.active:
            return
        s = self.session
        for ev in s.tick():
            if ev == "done":
                self._complete()
                return
            if ev == "break_end":
                self.break_armed = False
                beep(880, 120)
                self._raise()
                self._set_pool()
                self.oracle.say_from(FOCUS)
        rem = s.remaining()
        m, sec = divmod(rem, 60)
        h, m = divmod(m, 60)
        big = ("%d:%02d:%02d" % (h, m, sec)) if h else ("%02d:%02d" % (m, sec))
        if s.on_break:
            label = "on break"
        elif s.break_ms == 0:
            label = "no breaks"
        else:
            label = "%d break%s left" % (s.breaks_left, "" if s.breaks_left == 1 else "s")
        self.run_ring.set(rem / s.phase_len(), big, label)
        free = time.strftime("%H:%M", time.localtime(time.time() + s.total_left()))
        self.run_end.config(text="free at %s" % free)
        self._refresh_break()
        self.oracle.label.config(cursor="hand2")
        self.root.after(1000, self._loop)

    def _her_click(self):
        """Clicking her text during a session gives a new line from the bank."""
        if self.session.active:
            self.oracle.say(bank_line())

    def _poll(self):
        """2 s enforcement tick (cheap ctypes snapshot)."""
        if not self.session.active:
            return
        games, tools = self.session.enforce()
        if tools:
            beep(250, 200)
            self.oracle.say_from(SEALED, n=tools[0])
        elif games:
            beep(330, 160)
            self.oracle.say_from(CAUGHT, n=os.path.splitext(games[0])[0])
        self.root.after(2000, self._poll)

    def _heal(self):
        if not self.session.active:
            return
        self.session.heal()
        self.root.after(30000, self._heal)

    def _complete(self):
        melody(SOUND_DONE)
        self._raise()
        self.oracle.pool = lambda: IDLE
        self.oracle.label.config(cursor="arrow")
        self.show("home")
        self.oracle.say_from(DONE)

    def _raise(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(400, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    def _on_close(self):
        if self.session.active:
            beep(330, 120)
            self.oracle.say_from(REFUSE)
            return
        self.root.destroy()

    # --------------------------------------------------------------- settings
    def _build_settings(self):
        f = self.settings = tk.Frame(self.body, bg=BG)
        tabs = tk.Frame(f, bg=BG)
        tabs.pack(fill="x", padx=S(24), pady=(S(24), 0))
        self.tab_btns = {}
        for name in ("Programs", "Websites", "Presets", "About"):
            col = tk.Frame(tabs, bg=BG)
            col.pack(side="left", padx=(0, S(16)))
            b = tk.Label(col, text=name.lower(), bg=BG, fg=DIM, font=(MONO, 10), cursor="hand2")
            b.pack(pady=(0, S(8)))
            bar = tk.Frame(col, bg=BG, height=S(2))
            bar.pack(fill="x")
            b.bind("<Button-1>", lambda e, n=name: self._tab(n))
            b.bind("<Enter>", lambda e, n=name: n != self.tab_name and self.tab_btns[n][0].config(fg=FG))
            b.bind("<Leave>", lambda e, n=name: n != self.tab_name and self.tab_btns[n][0].config(fg=DIM))
            self.tab_btns[name] = (b, bar)
        tk.Frame(f, bg=LINE, height=1).pack(fill="x", padx=S(24))
        self.tab_body = tk.Frame(f, bg=BG)
        self.tab_body.pack(fill="both", expand=True, padx=S(24), pady=(S(16), 0))
        self.admin_lbl = tk.Label(f, text="", bg=BG, font=(MONO, 8), anchor="w")
        self.admin_lbl.pack(fill="x", padx=S(24), pady=(0, S(12)))
        self.tab_name = "Programs"

    def _refresh_settings(self):
        if is_admin():
            self.admin_lbl.config(text="● administrator  ·  full blocking", fg=DIM)
        else:
            self.admin_lbl.config(text="○ not administrator  ·  programs closed, sites not blocked", fg=DIM)
        self._tab(self.tab_name)

    def _listbox(self, parent, h=8, multi=False):
        return tk.Listbox(parent, bg=SURFACE, fg=FG, selectbackground=ACCENT_DIM,
                          selectforeground=FG, relief="flat", bd=0,
                          highlightthickness=1, highlightbackground=LINE,
                          highlightcolor=LINE, activestyle="none", height=h,
                          font=(MONO, 10), selectmode="multiple" if multi else "browse")

    def _entry(self, parent, width=None):
        e = tk.Entry(parent, bg=SURFACE, fg=FG, insertbackground=ACCENT_HI, insertwidth=S(2),
                     relief="flat", highlightthickness=1, highlightbackground=LINE,
                     highlightcolor=ACCENT, font=(MONO, 10))
        if width:
            e.config(width=width)
        return e

    def _note(self, parent, text):
        tk.Label(parent, text=text, bg=BG, fg=DIM, font=(UI, 9), anchor="w",
                 justify="left", wraplength=S(400)).pack(fill="x", pady=(S(12), 0))

    def _tab(self, name):
        self.tab_name = name
        for n, (b, bar) in self.tab_btns.items():
            b.config(fg=FG if n == name else DIM)
            bar.config(bg=ACCENT if n == name else BG)
        for w in self.tab_body.winfo_children():
            w.destroy()
        getattr(self, "_tab_" + name.lower())(self.tab_body)

    def _tab_programs(self, p):
        lb = self._listbox(p)
        lb.pack(fill="both", expand=True)
        items = [("exes", e) for e in self.cfg["exes"]] + [("dirs", d) for d in self.cfg["dirs"]]
        for kind, v in items:
            lb.insert("end", ("  " + v) if kind == "exes" else ("  ▸ everything in " + v.rstrip("\\")))

        def remove():
            for i in reversed(lb.curselection()):
                kind, v = items[i]
                self.cfg[kind].remove(v)
            self._save_cfg()
            self._tab("Programs")

        def add_manual(*_):
            raw = e.get().strip().strip('"').lower()
            e.delete(0, "end")
            if not raw:
                return
            if any(ch in raw for ch in '\\/:*?"<>|'):
                self.oracle.say("A name, not a path. Just the program's name, please.")
                return
            name = raw if raw.endswith(".exe") else raw + ".exe"
            if name == ".exe":
                return
            if name in PROTECTED:
                self.oracle.say("That one is protected. I will not touch it.")
                return
            if name not in self.cfg["exes"]:
                self.cfg["exes"].append(name)
                self._save_cfg()
            self._tab("Programs")

        manual = tk.Frame(p, bg=BG)
        manual.pack(fill="x", pady=(S(12), 0))
        e = self._entry(manual)
        e.pack(side="left", fill="x", expand=True, ipady=S(8))
        e.bind("<Return>", add_manual)
        Pill(manual, "Add", add_manual, w=70, h=34).pack(side="left", padx=(S(8), 0))

        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=(S(12), 0))
        Pill(row, "Browse…", self._pick_file, w=110, h=36).pack(side="left")
        Pill(row, "Running…", self._pick_running, w=110, h=36).pack(side="left", padx=S(8))
        Pill(row, "Remove", remove, w=96, h=36).pack(side="left")
        self._note(p, "Type a name like game or game.exe: every process with that name is closed "
                      "during focus. Browse or Running also block the whole folder, so renamed "
                      "copies are caught. Task Manager and Windows system processes can never be blocked.")

    def _tab_websites(self, p):
        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=(0, S(12)))
        e = self._entry(row)
        e.pack(side="left", fill="x", expand=True, ipady=S(8))
        lb = self._listbox(p)

        def add(*_):
            d = _clean_domain(e.get())
            if d and "." in d and d not in self.cfg["sites"]:
                self.cfg["sites"].append(d)
                self._save_cfg()
                lb.insert("end", "  " + d)
            e.delete(0, "end")
        e.bind("<Return>", add)
        Pill(row, "Add", add, w=70, h=34).pack(side="left", padx=(S(8), 0))
        lb.pack(fill="both", expand=True)
        for s in self.cfg["sites"]:
            lb.insert("end", "  " + s)

        def remove():
            for i in reversed(lb.curselection()):
                del self.cfg["sites"][i]
                lb.delete(i)
            self._save_cfg()
        Pill(p, "Remove", remove, w=96, h=36).pack(anchor="w", pady=(S(12), 0))
        self._note(p, "Type a site like youtube.com and press Enter (www., m. and "
                      "short links are covered). Needs administrator. Restart your "
                      "browser if a site still loads.")

    def _preset_row(self, pr):
        return " %-14s %4d min   %d break%s" % (pr["name"], pr["focus"], pr["breaks"],
                                                 "" if pr["breaks"] == 1 else "s")

    def _tab_presets(self, p):
        lb = self._listbox(p, h=4)
        lb.pack(fill="x")
        for pr in self.cfg["presets"]:
            lb.insert("end", self._preset_row(pr))
        form = tk.Frame(p, bg=BG)
        form.pack(fill="x", pady=(S(12), 0))
        fields = {}
        for key, label, hint in PRESET_FIELDS:
            top = tk.Frame(form, bg=BG)
            top.pack(fill="x", pady=(S(8), S(4)))
            tk.Label(top, text=label, bg=BG, fg=DIM, font=(UI, 9), anchor="w").pack(side="left")
            if hint:
                tk.Label(top, text=hint, bg=BG, fg=FAINT, font=(UI, 8), anchor="e").pack(side="right")
            ent = self._entry(form)
            if key in PRESET_DIGITS:              # number fields: digits 0-9 only
                ent.config(validate="key", validatecommand=(
                    ent.register(lambda t, n=PRESET_DIGITS[key]: digits_only(t, n)), "%P"))
            ent.pack(fill="x", ipady=S(4))
            fields[key] = ent

        def fill(*_):
            sel = lb.curselection()
            if not sel:
                return
            pr = self.cfg["presets"][sel[0]]
            for k, ent in fields.items():
                ent.delete(0, "end")
                ent.insert(0, str(pr[k]))
        lb.bind("<<ListboxSelect>>", fill)

        def read():
            if not all(digits_only(fields[k].get(), n) for k, n in PRESET_DIGITS.items()):
                self.oracle.say("Numbers, please. Minutes are not poetry.")
                return None
            try:
                name = fields["name"].get().strip()[:14] or "Preset"
                focus = max(1, min(MAX_MIN, int(fields["focus"].get())))
                breaks = max(0, min(12, int(fields["breaks"].get() or 0)))
                brk = max(0, min(120, int(fields["brk"].get() or 0)))
            except ValueError:
                self.oracle.say("Numbers, please. Minutes are not poetry.")
                return None
            if breaks and not brk:
                self.oracle.say("A break needs minutes. Give it a length.")
                return None
            return {"name": name, "focus": focus, "breaks": breaks, "brk": brk}

        def save_new():
            pr = read()
            if pr:
                self.cfg["presets"].append(pr)
                self._save_cfg()
                self._tab("Presets")

        def update():
            sel, pr = lb.curselection(), read()
            if sel and pr:
                self.cfg["presets"][sel[0]] = pr
                self._save_cfg()
                self._tab("Presets")

        def delete():
            sel = lb.curselection()
            if sel and len(self.cfg["presets"]) > 1:
                del self.cfg["presets"][sel[0]]
                self.cfg["sel"] = 0
                self._save_cfg()
                self._tab("Presets")

        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=(S(12), 0))
        Pill(row, "Save new", save_new, w=104, h=36).pack(side="left")
        Pill(row, "Update", update, w=96, h=36).pack(side="left", padx=S(8))
        Pill(row, "Delete", delete, w=96, h=36).pack(side="left")
        self._note(p, "Time and Break Time are minutes. The first four presets appear on the timer screen.")

    def _add_programs(self, paths):
        """paths: full exe paths (or bare names if the path is unknown)."""
        for path in paths:
            n = os.path.basename(path).lower()
            if n.endswith(".exe") and n not in PROTECTED and n not in self.cfg["exes"]:
                self.cfg["exes"].append(n)
            d = os.path.dirname(path)
            if d and blockable_dir(d):
                nd = _norm_dir(d)
                if nd not in self.cfg["dirs"]:
                    self.cfg["dirs"].append(nd)
        self._save_cfg()
        self._tab("Programs")

    def _pick_file(self):
        p = filedialog.askopenfilename(title="Choose a program to block",
                                       filetypes=[("Programs", "*.exe")])
        if p:
            self._add_programs([p])

    def _pick_running(self):
        found = {}
        for pid, n, _ in processes():
            if n.endswith(".exe") and n not in PROTECTED and n not in SEAL and n not in found:
                found[n] = pid
        names = sorted(found)
        if not names:
            self.oracle.say("I see nothing running worth taking from you.")
            return
        win = tk.Toplevel(self.root, bg=BG)
        win.title("Running programs")
        win.geometry("%dx%d" % (S(340), S(460)))
        win.transient(self.root)
        dark_titlebar(win)
        tk.Label(win, text="Select programs to block", bg=BG, fg=FG,
                 font=(UI, 11, "bold")).pack(anchor="w", padx=S(16), pady=(S(16), S(12)))
        lb = self._listbox(win, multi=True)
        lb.pack(fill="both", expand=True, padx=S(16))
        for n in names:
            lb.insert("end", "  " + n)

        def add():
            picks = []
            for i in lb.curselection():
                n = names[i]
                picks.append(image_path(found[n]) or n)
            self._add_programs(picks)
            win.destroy()
        Pill(win, "Add selected", add, w=160, h=40, kind="accent").pack(pady=S(16))

    def _tab_about(self, p):
        Wordmark(p, 26, blink=False).pack(anchor="w", pady=(S(4), S(4)))
        tk.Label(p, text="version %s" % VERSION, bg=BG, fg=DIM, font=(MONO, 9)).pack(anchor="w")
        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=(S(16), 0))
        Pill(row, "Check for updates", self._check_updates, w=170, h=38, kind="accent").pack(side="left")
        self.auto_btn = Pill(row, "", self._toggle_auto, w=150, h=38)
        self.auto_btn.pack(side="left", padx=S(8))
        self.about_lbl = tk.Label(p, text="", bg=BG, fg=DIM, font=(MONO, 9), anchor="w",
                                  justify="left", wraplength=S(400))
        self.about_lbl.pack(fill="x", pady=(S(16), 0))
        self._note(p, "Updates come from this app's GitHub Releases. They are only ever "
                      "installed between sessions, never during one.")
        self._about_status()

    def _about_status(self):
        try:
            self.auto_btn.set_text("auto-update: %s" % ("on" if self.cfg.get("auto_update") else "off"))
            u = self.updater
            msg = {
                "idle": "",
                "checking": "Asking GitHub for a newer act…",
                "latest": "You already have the latest version%s." % ((" (%s)" % u.tag) if u.tag else ""),
                "downloading": "Downloading %s…" % u.tag,
                "ready": "%s is ready. Installing…" % u.tag,
                "error": "Could not reach GitHub. Try again later.",
                "dev": "Updates only work in the built Ave.exe.",
            }[u.state]
            self.about_lbl.config(text=msg)
        except Exception:
            pass

    def _check_updates(self):
        if self.session.active:
            return
        if self.updater.state in ("latest", "error", "dev"):
            self.updater.state = "idle"
        self.updater.start(manual=True)
        self._about_status()
        self.root.after(2000, self._watch_update)

    def _toggle_auto(self):
        self.cfg["auto_update"] = not self.cfg.get("auto_update")
        self._save_cfg()
        self._about_status()

    def _save_cfg(self):
        save_json(CONFIG_FILE, self.cfg)


# =============================================================================
# Single instance + guard takeover
# =============================================================================

_LOCK = None


def acquire_lock():
    global _LOCK
    if not IS_WIN:
        _LOCK = True
        return True
    k = ctypes.windll.kernel32
    k.CreateMutexW.restype = ctypes.c_void_p
    h = k.CreateMutexW(None, False, "Local\\AveSingleton")
    if k.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        k.CloseHandle(ctypes.c_void_p(h))
        return False
    _LOCK = h
    return True


def release_lock():
    global _LOCK
    if IS_WIN and _LOCK:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_LOCK))
    _LOCK = None


def focus_existing():
    try:
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, APP)
        if hwnd:
            u.ShowWindow(hwnd, 9)
            u.SetForegroundWindow(hwnd)
    except Exception:
        pass


def take_over_if_frozen():
    """Guard tick: if the running Ave stopped its heartbeat (suspended or hung)
    for 2.5 minutes, end it and take its place."""
    st = state_load()
    if not st.get("active"):
        return False
    now, saved = ticks(), st.get("saved_tick", 0)
    if now < saved or now - saved < 150000:
        return False
    pid = st.get("pid")
    if not any(p == pid and n in ("ave.exe", "python.exe", "pythonw.exe")
               for p, n, _ in processes()):
        return False
    kill(pid)
    for _ in range(10):
        time.sleep(0.5)
        if acquire_lock():
            return True
    return False


def main():
    if "--cleanup" in sys.argv:
        cleanup_everything()
        return
    guard = "--guard" in sys.argv
    if not acquire_lock():
        if not guard:
            focus_existing()
            return
        if not take_over_if_frozen():
            return
    st = state_load()
    if guard and not st.get("active"):
        cleanup_everything()        # leftover guard with no session: tidy up, stay closed
        return
    if guard and st.get("admin") and not is_admin() and guard_exists():
        return                      # login copy without admin: the elevated guard takes over
    if not st.get("active"):
        ensure_backup()
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    setup_fonts(root)
    App(root, st)
    root.mainloop()


if __name__ == "__main__":
    main()
