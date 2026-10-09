"""Unicode "fonts" for a professional look inside Telegram.

Telegram does not let bots pick a typeface, so headings use the Unicode
*Mathematical Sans-Serif Bold* block and labels use *small caps*.  Only plain
ASCII letters/digits are converted; everything else is left untouched.
"""

from __future__ import annotations

_BOLD_UPPER = 0x1D5D4  # 𝗔
_BOLD_LOWER = 0x1D5EE  # 𝗮
_BOLD_DIGIT = 0x1D7EC  # 𝟬

_SMALL_CAPS = dict(zip("abcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"))


def bold(text: str) -> str:
    out = []
    for ch in text:
        if "A" <= ch <= "Z":
            out.append(chr(_BOLD_UPPER + ord(ch) - 65))
        elif "a" <= ch <= "z":
            out.append(chr(_BOLD_LOWER + ord(ch) - 97))
        elif "0" <= ch <= "9":
            out.append(chr(_BOLD_DIGIT + ord(ch) - 48))
        else:
            out.append(ch)
    return "".join(out)


def small_caps(text: str) -> str:
    return "".join(_SMALL_CAPS.get(ch, _SMALL_CAPS.get(ch.lower(), ch)) for ch in text)
