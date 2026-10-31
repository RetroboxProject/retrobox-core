"""Texts of the setup screen, in the most common European languages.

The language is EmulationStation's own (``Language`` in es_settings.cfg) when
it was set there, else the system locale (``LANGUAGE``, ``LC_ALL``,
``LC_MESSAGES``, ``LANG``), else English. Only the language part of a locale
is used (``pt_BR`` -> ``pt``). Key names (A, Enter, Esc, Ctrl...) are not
translated: they are printed on the keys and the pad.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


class Texts(NamedTuple):
    """Every text the screen shows, with ``str.format`` fields."""

    ask: str  # {label}
    installing: str  # {label}
    failed: str  # {label}
    done: str  # {label}
    yes: str
    no: str
    ok: str
    select: str
    cancel: str
    type_here: str
    copy_paste: str
    scroll: str
    continue_: str
    copy_log: str
    full_log: str
    copied: str  # {lines}
    cannot_run: str  # {error}
    still_missing: str  # {path}
    exit_status: str  # {status}


DEFAULT_LANGUAGE: Final = "en"

TEXTS: Final[dict[str, Texts]] = {
    "en": Texts(
        ask="The emulator {label} is not installed. Install it?",
        installing="Installing {label}, please wait",
        failed="Could not install {label}",
        done="{label} was installed successfully",
        yes="Yes", no="No", ok="OK",
        select="select", cancel="cancel",
        type_here="Type here if the installer asks (e.g. sudo password)",
        copy_paste="copy / paste", scroll="scroll",
        continue_="continue", copy_log="copy log", full_log="Full log",
        copied="Lines copied to the clipboard: {lines}",
        cannot_run="Cannot run the installer: {error}",
        still_missing="The installer finished, but {path} is still missing.",
        exit_status="The installer exited with status {status}.",
    ),
    "es": Texts(
        ask="El emulador {label} no está instalado. ¿Quieres instalarlo?",
        installing="Instalando {label}, espera, por favor",
        failed="No se ha podido instalar {label}",
        done="{label} se ha instalado correctamente",
        yes="Sí", no="No", ok="Aceptar",
        select="seleccionar", cancel="cancelar",
        type_here="Escribe aquí si el instalador lo pide (p. ej. la contraseña de sudo)",
        copy_paste="copiar / pegar", scroll="desplazar",
        continue_="continuar", copy_log="copiar el registro", full_log="Registro completo",
        copied="Líneas copiadas al portapapeles: {lines}",
        cannot_run="No se puede ejecutar el instalador: {error}",
        still_missing="El instalador ha terminado, pero sigue faltando {path}.",
        exit_status="El instalador ha terminado con el código {status}.",
    ),
    "ca": Texts(
        ask="L'emulador {label} no està instal·lat. Vols instal·lar-lo?",
        installing="S'està instal·lant {label}, espera",
        failed="No s'ha pogut instal·lar {label}",
        done="{label} s'ha instal·lat correctament",
        yes="Sí", no="No", ok="D'acord",
        select="seleccionar", cancel="cancel·lar",
        type_here="Escriu aquí si l'instal·lador ho demana (p. ex. la contrasenya de sudo)",
        copy_paste="copiar / enganxar", scroll="desplaçar",
        continue_="continuar", copy_log="copiar el registre", full_log="Registre complet",
        copied="Línies copiades al porta-retalls: {lines}",
        cannot_run="No es pot executar l'instal·lador: {error}",
        still_missing="L'instal·lador ha acabat, però encara falta {path}.",
        exit_status="L'instal·lador ha acabat amb el codi {status}.",
    ),
    "gl": Texts(
        ask="O emulador {label} non está instalado. Queres instalalo?",
        installing="Instalando {label}, agarda, por favor",
        failed="Non se puido instalar {label}",
        done="{label} instalouse correctamente",
        yes="Si", no="Non", ok="Aceptar",
        select="seleccionar", cancel="cancelar",
        type_here="Escribe aquí se o instalador o pide (p. ex. o contrasinal de sudo)",
        copy_paste="copiar / pegar", scroll="desprazar",
        continue_="continuar", copy_log="copiar o rexistro", full_log="Rexistro completo",
        copied="Liñas copiadas no portapapeis: {lines}",
        cannot_run="Non se pode executar o instalador: {error}",
        still_missing="O instalador rematou, pero aínda falta {path}.",
        exit_status="O instalador rematou co código {status}.",
    ),
    "pt": Texts(
        ask="O emulador {label} não está instalado. Instalar?",
        installing="Instalando {label}, aguarde",
        failed="Não foi possível instalar {label}",
        done="{label} foi instalado com sucesso",
        yes="Sim", no="Não", ok="OK",
        select="selecionar", cancel="cancelar",
        type_here="Escreva aqui se o instalador pedir (p. ex. a senha do sudo)",
        copy_paste="copiar / colar", scroll="deslocar",
        continue_="continuar", copy_log="copiar o log", full_log="Log completo",
        copied="Linhas copiadas para a área de transferência: {lines}",
        cannot_run="Não é possível executar o instalador: {error}",
        still_missing="O instalador terminou, mas {path} continua em falta.",
        exit_status="O instalador terminou com o código {status}.",
    ),
    "fr": Texts(
        ask="L'émulateur {label} n'est pas installé. L'installer ?",
        installing="Installation de {label}, veuillez patienter",
        failed="Impossible d'installer {label}",
        done="{label} a été installé avec succès",
        yes="Oui", no="Non", ok="OK",
        select="sélectionner", cancel="annuler",
        type_here="Tapez ici si l'installateur le demande (p. ex. le mot de passe sudo)",
        copy_paste="copier / coller", scroll="défiler",
        continue_="continuer", copy_log="copier le journal", full_log="Journal complet",
        copied="Lignes copiées dans le presse-papiers : {lines}",
        cannot_run="Impossible de lancer l'installateur : {error}",
        still_missing="L'installateur a terminé, mais {path} est toujours absent.",
        exit_status="L'installateur s'est terminé avec le code {status}.",
    ),
    "it": Texts(
        ask="L'emulatore {label} non è installato. Installarlo?",
        installing="Installazione di {label} in corso, attendere",
        failed="Impossibile installare {label}",
        done="{label} è stato installato correttamente",
        yes="Sì", no="No", ok="OK",
        select="seleziona", cancel="annulla",
        type_here="Scrivi qui se l'installer lo chiede (ad es. la password di sudo)",
        copy_paste="copia / incolla", scroll="scorri",
        continue_="continua", copy_log="copia il log", full_log="Log completo",
        copied="Righe copiate negli appunti: {lines}",
        cannot_run="Impossibile avviare l'installer: {error}",
        still_missing="L'installer ha terminato, ma {path} manca ancora.",
        exit_status="L'installer è terminato con il codice {status}.",
    ),
    "de": Texts(
        ask="Der Emulator {label} ist nicht installiert. Jetzt installieren?",
        installing="{label} wird installiert, bitte warten",
        failed="{label} konnte nicht installiert werden",
        done="{label} wurde erfolgreich installiert",
        yes="Ja", no="Nein", ok="OK",
        select="auswählen", cancel="abbrechen",
        type_here="Hier tippen, wenn das Installationsprogramm danach fragt (z. B. sudo-Passwort)",
        copy_paste="kopieren / einfügen", scroll="blättern",
        continue_="weiter", copy_log="Protokoll kopieren", full_log="Vollständiges Protokoll",
        copied="In die Zwischenablage kopierte Zeilen: {lines}",
        cannot_run="Das Installationsprogramm kann nicht gestartet werden: {error}",
        still_missing="Das Installationsprogramm ist fertig, aber {path} fehlt noch.",
        exit_status="Das Installationsprogramm wurde mit Status {status} beendet.",
    ),
    "nl": Texts(
        ask="De emulator {label} is niet geïnstalleerd. Nu installeren?",
        installing="{label} wordt geïnstalleerd, even geduld",
        failed="{label} kon niet worden geïnstalleerd",
        done="{label} is met succes geïnstalleerd",
        yes="Ja", no="Nee", ok="OK",
        select="selecteren", cancel="annuleren",
        type_here="Typ hier als het installatieprogramma erom vraagt (bijv. het sudo-wachtwoord)",
        copy_paste="kopiëren / plakken", scroll="scrollen",
        continue_="doorgaan", copy_log="log kopiëren", full_log="Volledige log",
        copied="Regels gekopieerd naar het klembord: {lines}",
        cannot_run="Kan het installatieprogramma niet starten: {error}",
        still_missing="Het installatieprogramma is klaar, maar {path} ontbreekt nog.",
        exit_status="Het installatieprogramma is gestopt met status {status}.",
    ),
    "pl": Texts(
        ask="Emulator {label} nie jest zainstalowany. Zainstalować?",
        installing="Instalowanie {label}, proszę czekać",
        failed="Nie udało się zainstalować {label}",
        done="Zainstalowano {label}",
        yes="Tak", no="Nie", ok="OK",
        select="wybierz", cancel="anuluj",
        type_here="Pisz tutaj, jeśli instalator o to poprosi (np. hasło sudo)",
        copy_paste="kopiuj / wklej", scroll="przewijaj",
        continue_="dalej", copy_log="kopiuj dziennik", full_log="Pełny dziennik",
        copied="Wiersze skopiowane do schowka: {lines}",
        cannot_run="Nie można uruchomić instalatora: {error}",
        still_missing="Instalator zakończył pracę, ale nadal brakuje {path}.",
        exit_status="Instalator zakończył pracę z kodem {status}.",
    ),
    "ru": Texts(
        ask="Эмулятор {label} не установлен. Установить?",
        installing="Установка {label}, подождите",
        failed="Не удалось установить {label}",
        done="{label} успешно установлен",
        yes="Да", no="Нет", ok="ОК",
        select="выбрать", cancel="отмена",
        type_here="Вводите здесь, если установщик попросит (например, пароль sudo)",
        copy_paste="копировать / вставить", scroll="прокрутка",
        continue_="продолжить", copy_log="копировать журнал", full_log="Полный журнал",
        copied="Скопировано строк в буфер обмена: {lines}",
        cannot_run="Не удалось запустить установщик: {error}",
        still_missing="Установщик завершил работу, но {path} по-прежнему отсутствует.",
        exit_status="Установщик завершился с кодом {status}.",
    ),
}

_LOCALE_VARIABLES: Final = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")


def _code(locale: str) -> str:
    """``es_ES.UTF-8`` -> ``es``; empty for the C/POSIX locale."""
    code = locale.strip().split(".", 1)[0].split("@", 1)[0].replace("-", "_").split("_", 1)[0]
    return "" if code.upper() in ("", "C", "POSIX") else code.lower()


def _candidates(es_language: str, environ: Mapping[str, str]) -> Iterable[str]:
    """Locales to try, most preferred first."""
    yield es_language
    for variable in _LOCALE_VARIABLES:
        # LANGUAGE is a colon-separated list of preferences
        yield from environ.get(variable, "").split(":")


def pick_language(es_language: str = "", environ: Mapping[str, str] | None = None) -> str:
    """The first supported language among ES's setting and the system locale.

    Args:
        es_language: ``Language`` of es_settings.cfg (e.g. ``es_ES``), if set.
        environ: The environment to read the locale from (default: os.environ).

    Returns:
        A key of TEXTS; DEFAULT_LANGUAGE when nothing better matches.
    """
    environ = os.environ if environ is None else environ
    for candidate in _candidates(es_language, environ):
        code = _code(candidate)
        if code in TEXTS:
            return code
    return DEFAULT_LANGUAGE


def texts_for(language: str) -> Texts:
    """The texts of ``language`` (a code or a whole locale), English if unknown."""
    return TEXTS.get(_code(language), TEXTS[DEFAULT_LANGUAGE])
