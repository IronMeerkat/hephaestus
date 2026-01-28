import logging

NORM = '\033[0m'
BOLD = '\033[01m'
BG_RED = '\033[41m'

RED = '\033[31m'
BLUE = '\033[34m'
LIGHT_BLUE = '\033[94m'
WHITE = '\033[97m'
GRAY = '\033[37m'
BROWN = '\033[33m'
DARK_GREEN = '\033[32m'
GREEN = '\033[92m'
YELLOW = '\033[93m'



class CustomFormatter(logging.Formatter):
    _name_colors = {
        logging.DEBUG: f'{BROWN}',
        logging.INFO: f'{BROWN}',
        logging.WARNING: f'{BOLD}{RED}',
        logging.ERROR: f'{BOLD}{BG_RED}',
        logging.FATAL: f'{BOLD}{BG_RED}',
    }

    _name_emojis = {
        logging.DEBUG: '🪲',
        logging.INFO: '☁️',
        logging.WARNING: '⚠️',
        logging.ERROR: '❌',
        logging.FATAL: '💀'
    }
    _msg_color = YELLOW

    def __init__(self, *args, **kwargs):
        # Yaml parsing doesn't work properly with escape
        # chars for coloring. So The format is hard coded.
        # Any *args, **kwargs passed to the factory are ignored.
        fmt = (f'{WHITE}%(asctime)s{NORM} '
               f'%(level_emoji)s {NORM} '
               f'[{DARK_GREEN}%(name)s{NORM}] '
               f'{self._msg_color}%(message)s{NORM}')
        super().__init__(fmt=fmt, datefmt=None, style='%')

    def format(self, record):
        if record.exc_info:
            exc_text = record.exc_text or self.formatException(record.exc_info)
            record.exc_text = self.colorize_exception(exc_text)

        record.name_color = self._name_colors[record.levelno]
        record.level_emoji = self._name_emojis[record.levelno]

        msg = super().format(record)

        # Cleanup for following handlers
        if record.exc_text:
            record.exc_text = exc_text
        del record.name_color

        return msg

    def formatMessage(self, record):
        msg = super().formatMessage(record)

        # if ctx:
        #     context = f'    {NORM}Context({ctx})'
        #     total_length = len(record.message) + len(context)
        #     if total_length > 200 or '\n' in record.message:
        #         msg = f'{msg}\n{context}'
        #     else:
        #         msg += context

        if '\n' in msg:
            first, *others = msg.split('\n')
            meta = self._extract_metadata(first)
            msg = '\n'.join((
                first,
                *(f'{meta}{line}' for line in others),

            ))
        return msg

    def _extract_metadata(self, s):
        meta = s[:s.find(']')] + f'> {self._msg_color}'
        return meta

    @staticmethod
    def colorize_exception(exc_text):
        txt = exc_text.split('\n')
        python_exc_passed = False
        for i, line in enumerate(txt):
            stripped = line.strip()

            if stripped.startswith('Traceback'):
                txt[i] = f'{RED}{line}{NORM}'

            elif stripped.startswith('File '):
                file_start = line.find('"')
                file_end = line.find('"', file_start+1)+1
                line_start = file_end + 7
                line_end = line.find(',', line_start+1)
                func_name = line_end + 5
                txt[i] = (
                    f'{LIGHT_BLUE}{line[:file_start]}'
                    f'{RED}{line[file_start:file_end]}'
                    f'{LIGHT_BLUE}{line[file_end:line_start]}'
                    f'{BOLD}{RED}{line[line_start:line_end]}{NORM}'
                    f'{LIGHT_BLUE}{line[line_end:func_name]}'
                    f'{BOLD}{RED}{line[func_name:]}{NORM}'
                )

            elif stripped.startswith('raise'):
                name_start = line.find('raise') + 6
                msg_start = line.find('(', name_start)
                if msg_start > 0:
                    txt[i] = (
                        f'{LIGHT_BLUE}{line[:name_start]}'
                        f'{BOLD}{RED}{line[name_start:msg_start]}'
                        f'{NORM}{RED}('
                        f'{WHITE}{line[msg_start+1:-1]}'
                        f'{RED}){NORM}'
                    )

            elif not line.startswith(' ') and not python_exc_passed:
                python_exc_passed = True
                name_end = line.find(':')
                txt[i] = (
                    f'{BOLD}{RED}{line[:name_end]}: '
                    f'{WHITE}{line[name_end+2:]}{NORM}'
                )

            else:
                txt[i] = (
                    line.replace('=', f'{GRAY}={NORM}')
                )
        return '\n'.join(txt)