"""Offline text-to-speech with the Windows male voice; the extension adds the deep/scary effects."""
import re
import subprocess

PS = r"""
$t = [Console]::In.ReadToEnd()
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$male = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Gender -eq 'Male' -and $_.VoiceInfo.Culture.Name -like 'en*' } | Select-Object -First 1
if ($male) { $s.SelectVoice($male.VoiceInfo.Name) }
$s.Rate = -1
$ms = New-Object System.IO.MemoryStream
$s.SetOutputToWaveStream($ms)
$s.Speak($t)
$out = [Console]::OpenStandardOutput()
$out.Write($ms.ToArray(), 0, [int]$ms.Length)
$out.Flush()
"""


def can_speak(text: str) -> bool:
    # Only English goes to the Windows voice; Indian scripts use the browser's voice for that language
    return not re.search(r"[؀-ۿऀ-෿᱐-᱿ꯀ-꯿]", text)


def synth(text: str) -> bytes:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", PS], input=text[:2500].encode("utf-8"),
                       capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or len(r.stdout) < 1000:
        raise RuntimeError("Windows speech failed: " + r.stderr.decode(errors="replace")[:200])
    return r.stdout
