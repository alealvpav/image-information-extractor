import argparse
import csv
import glob
import os
import sys
import csv_store
from geo_extractor import get_file_type, get_media_files, get_media_info
from geo_extractor import i18n
from geo_extractor.i18n import _

DEFAULT_MEDIA_DIR = "media"
DEFAULT_OUTPUT_FILE = "media_geo_information.csv"

# Nombres de las opciones en cada idioma; se aceptan los de los dos idiomas, pero la ayuda muestra los del actual
OPTION_NAMES = {
    "new": {"es": ("-n", "--nuevo"), "en": ("-n", "--new")},
    "update": {"es": ("-a", "--actualizar"), "en": ("-u", "--update")},
    "overwrite": {"es": ("-s", "--sobrescribir"), "en": ("-o", "--overwrite")},
}

def option(name):
    """Nombre largo de una opción en el idioma actual (para los mensajes)."""
    return OPTION_NAMES[name][i18n.get_language()][1]

def complete_path(text, state):
    matches = [m + os.sep if os.path.isdir(m) else m for m in glob.glob(os.path.expanduser(text) + "*")]
    return matches[state] if state < len(matches) else None

def enable_line_editing():
    # En Linux/macOS, readline permite usar las flechas, el historial y completar rutas con Tab.
    # En Windows no existe, pero la consola ya permite editar la línea
    try:
        import readline
    except ImportError:
        return
    readline.set_completer_delims(" \t\n;")
    readline.set_completer(complete_path)
    readline.parse_and_bind("tab: complete")

def normalize_path(path):
    # Quita las comillas que añaden "Copiar como ruta" en Windows o arrastrar la carpeta a la terminal en Linux,
    # y expande "~", "$HOME" y "%USERPROFILE%"
    path = path.strip().strip('"').strip("'")
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))

def ask_yes_no(question, default=None):
    yes_answers = ["s", "si", "sí", "y", "yes"]
    no_answers = ["n", "no"]
    answers = _("yes_no")
    if default and default.lower() in ("s", "y"):
        answers = _("yes_no_default_yes")
        yes_answers.append("")
    elif default and default.lower() == "n":
        answers = _("yes_no_default_no")
        no_answers.append("")
    while True:
        answer = input(f"{question} ({answers}): ").strip().lower()
        if answer in yes_answers:
            return True
        if answer in no_answers:
            return False

def check_media_dir(path):
    media_dir = normalize_path(path)
    if not os.path.isdir(media_dir):
        raise ValueError(_("error_folder_missing", path=media_dir))
    return media_dir

def resolve_new_csv_path(path):
    csv_path = normalize_path(path)
    if os.path.isdir(csv_path):
        csv_path = os.path.join(csv_path, DEFAULT_OUTPUT_FILE)
    if not csv_path.lower().endswith(".csv"):
        csv_path += ".csv"
    if not os.path.isdir(os.path.dirname(csv_path)):
        raise ValueError(_("error_csv_folder_missing", path=os.path.dirname(csv_path)))
    return csv_path

def load_existing_csv(path):
    csv_path = normalize_path(path)
    if not os.path.isfile(csv_path):
        raise ValueError(_("error_file_missing", path=csv_path))
    try:
        fieldnames, rows = csv_store.read_csv(csv_path)
    except (OSError, csv.Error) as e:
        raise ValueError(_("error_csv_unreadable", path=csv_path, error=e))
    if not csv_store.is_generated_csv(fieldnames):
        raise ValueError(_("error_not_generated_csv", path=csv_path, column=csv_store.FILE_NAME_COLUMN))
    return csv_path, fieldnames, rows

def ask_media_dir():
    while True:
        answer = input(_("prompt_media_dir", default=DEFAULT_MEDIA_DIR))
        try:
            return check_media_dir(answer or DEFAULT_MEDIA_DIR)
        except ValueError as e:
            print(f"{e} {_('try_again')}")

def ask_csv_mode():
    while True:
        answer = input(_("prompt_csv_mode")).strip().lower()
        if answer in ("", "n", "nuevo", "new"):
            return "new"
        if answer in ("a", "actualizar", "u", "update"):
            return "update"

def ask_new_csv_path():
    while True:
        answer = input(_("prompt_new_csv", default=DEFAULT_OUTPUT_FILE))
        try:
            csv_path = resolve_new_csv_path(answer or DEFAULT_OUTPUT_FILE)
        except ValueError as e:
            print(f"{e} {_('try_again')}")
            continue
        if not os.path.exists(csv_path) or ask_yes_no(_("confirm_overwrite", path=csv_path), "n"):
            return csv_path

def ask_existing_csv_path():
    while True:
        answer = input(_("prompt_existing_csv", default=DEFAULT_OUTPUT_FILE))
        try:
            return load_existing_csv(answer or DEFAULT_OUTPUT_FILE)
        except ValueError as e:
            print(f"{e} {_('try_again')}")

def extract_rows(media_dir, media_files):
    rows = []
    for media_file in media_files:
        media_path = os.path.join(media_dir, media_file)
        try:
            media_info = get_media_info(media_path)
        except Exception as e:
            print(_("file_unreadable", name=media_file, error=e))
            media_info = {}
        rows.append(csv_store.build_row(media_file, media_path, get_file_type(media_file), media_info))
    return rows

class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions, groups, _("usage_prefix") if prefix is None else prefix)

class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Los mensajes que genera argparse por su cuenta (combinaciones no válidas...) quedan en inglés
        self.print_usage(sys.stderr)
        self.exit(2, _("argparse_error", prog=self.prog, message=message))

def language_from_argv(argv):
    """El idioma tiene que conocerse antes de construir la ayuda, así que --lang se busca a mano."""
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None

def translate_options(argv, language):
    """Cambia las opciones escritas en el otro idioma (--new, --nuevo...) por las del idioma actual."""
    aliases = {}
    for names in OPTION_NAMES.values():
        for other in i18n.SUPPORTED_LANGUAGES:
            for alias, name in zip(names[other], names[language]):
                aliases[alias] = name
    translated = []
    for arg in argv:
        name, separator, value = arg.partition("=")
        translated.append(aliases.get(name, name) + separator + value)
    return translated

def parse_args(argv):
    language = i18n.language_from_code(language_from_argv(argv)) or i18n.detect_language()
    i18n.set_language(language)

    parser = ArgumentParser(description=_("description"), epilog=_("epilog"),
                            formatter_class=HelpFormatter, add_help=False)
    # Grupos propios para que los títulos salgan traducidos
    arguments = parser.add_argument_group(_("group_arguments"))
    arguments.add_argument("folder", nargs="?", metavar=_("metavar_folder"), help=_("help_folder"))
    options = parser.add_argument_group(_("group_options"))
    options.add_argument("-h", "--help", action="help", help=_("help_help"))
    csv_mode = options.add_mutually_exclusive_group()
    csv_mode.add_argument(*OPTION_NAMES["new"][language], dest="new", metavar="CSV", help=_("help_new"))
    csv_mode.add_argument(*OPTION_NAMES["update"][language], dest="update", metavar="CSV", help=_("help_update"))
    options.add_argument(*OPTION_NAMES["overwrite"][language], dest="overwrite", action="store_true",
                         help=_("help_overwrite", new=option("new")))
    options.add_argument("--lang", choices=i18n.SUPPORTED_LANGUAGES, help=_("help_lang"))

    args = parser.parse_args(translate_options(argv, language))
    if args.overwrite and not args.new:
        parser.error(_("overwrite_requires_new", overwrite=option("overwrite"), new=option("new")))
    return args

def new_csv_path_from_arg(path, overwrite):
    csv_path = resolve_new_csv_path(path)
    if os.path.exists(csv_path) and not overwrite:
        raise ValueError(_("error_csv_exists", path=csv_path, overwrite=option("overwrite"), update=option("update")))
    return csv_path

def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    enable_line_editing()

    # Lo que llega como argumento no se pregunta; si es incorrecto, se termina con un error en vez de volver a preguntar
    media_dir = check_media_dir(args.folder) if args.folder else ask_media_dir()
    media_files = get_media_files(media_dir)
    if not media_files:
        print(_("no_files", path=media_dir))
        return

    if args.new:
        mode, csv_path = "new", new_csv_path_from_arg(args.new, args.overwrite)
    elif args.update:
        mode = "update"
        csv_path, existing_fieldnames, existing_rows = load_existing_csv(args.update)
    else:
        mode = ask_csv_mode()
        if mode == "new":
            csv_path = ask_new_csv_path()
        else:
            csv_path, existing_fieldnames, existing_rows = ask_existing_csv_path()
    if mode == "new":
        existing_fieldnames, existing_rows = [], []

    new_rows = extract_rows(media_dir, media_files)
    rows, updated = csv_store.merge_rows(existing_rows, new_rows)
    csv_store.write_csv(csv_path, rows, existing_fieldnames)

    if mode == "update":
        print(_("csv_updated", new=len(new_rows) - updated, updated=updated, total=len(rows), path=csv_path))
    else:
        print(_("csv_created", count=len(new_rows), path=csv_path))

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n" + _("cancelled"))
        sys.exit(1)
    except ValueError as e:
        print(_("error", message=e), file=sys.stderr)
        sys.exit(1)
