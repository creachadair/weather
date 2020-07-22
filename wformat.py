##
## Name:     wformat.py
## Purpose:  API to fetch and format NWS weather reports.
##
## Copyright (C) 2004-2007 Michael J. Fromberger, All Rights Reserved.
##
## Permission is hereby granted, free of charge, to any person
## obtaining a copy of this software and associated documentation
## files (the "Software"), to deal in the Software without
## restriction, including without limitation the rights to use, copy,
## modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is
## furnished to do so, subject to the following conditions:
##
## The above copyright notice and this permission notice shall be
## included in all copies or substantial portions of the Software.
##
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
## EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
## MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
## NONINFRINGEMENT.  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
## HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
## WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
## DEALINGS IN THE SOFTWARE.
##
import os, sys, re, time, textwrap
from socket import socket, AF_INET, SOCK_STREAM

# --- Various regular expressions and constants
# These might need to be edited if the output format for the NWS
# reports changes.  BE CAREFUL when editing these.

# The expected format of the date and time for the weather data.
time_format = '%I:%M %p %a %b %d %Y'

# Width in characters of the status fields.
stat_width = 20

# Regular expression matching location and time information.
head_re = re.compile('(?i)Weather Conditions at (.+) on (.+) for (.+)\.\s*$')

# Regular expression matching named fields.
field_re = re.compile('(\w+)(?:\((.+)\))?$')

# Regular expression matching forecast location.
loc_re = re.compile('Forecast for (.+)\s*$', re.I)

# Regular expression matching forecast time information.
time_re = re.compile(
    '(?i)(\d+) (AM|PM) (\w{3,}) (\w{3}) (\w{3}) (\d+) (\d+)\s*$')

# Regular expression matching forecast text.
cast_re = re.compile('\.(.+?)\.\.\.(.+)$')

# Regular expression matching the "end-of-message" marker.
end_re = re.compile('\s*-----+\s*$')

# Regular expression matching the command prompt from the NWS interface.
sel_re = re.compile('Selection:')

_setup_pgm = (('wait', re.compile('Return to continue:')), ('send', '\n'),
              ('wait', re.compile('forecast city code--')), ('send', '\n'),
              ('wait/send', sel_re, 'C\n'), ('wait/send', sel_re, '4\n'))

default_host = 'rainmaker.wunderground.com'  # Host to connect to
default_port = 23  # Port to connect to
debug = os.getenv('DEBUG')

# {{ fetch_weather(station, host, port)


def fetch_weather(station, host=default_host, port=default_port):
    """Retrieve the text of the current weather report for the given
    weather station.  If provided, host and port will override the
    defaults for the server to connect to."""

    return run_program(
        _setup_pgm + (('wait/send', sel_re, '1\n'),
                      ('wait/send', sel_re, '1\n'),
                      ('wait', re.compile('3-letter city code:')),
                      ('send', "%s\n" % station.upper()),
                      ('read', re.compile('CITY FORECAST MENU')),
                      ('wait/send', sel_re, 'X\n'), ('quit', )), host, port)


# }}

# {{ fetch_city_codes(state, host, port)


def fetch_city_codes(state, host=default_host, port=default_port):
    """Retrieve the text of the city code listing for a given state,
    given by two-letter postal abbreviation."""

    out = run_program(
        _setup_pgm + (('wait/send', sel_re, '1\n'),
                      ('wait/send', sel_re, '3\n'),
                      ('wait', re.compile('Enter 2-letter state code:')),
                      ('send', '%s\n' % state.upper()),
                      ('wait', re.compile('State\s+Code\s+City\s*-+')),
                      ('read/resume', re.compile('CITY FORECAST MENU'),
                       re.compile('Press Return.+X to exit:'), '\n'),
                      ('wait/send', sel_re, 'X\n'), ('quit', )), host, port)

    return str.join('\n', [p.strip() for p in out[0].split('\n')])


# }}

# {{ fetch_state_codes(host, port)


def fetch_state_codes(host=default_host, port=default_port):
    """Retrieve the text of the two-letter state code listing."""

    out = run_program(
        _setup_pgm + (('wait/send', sel_re, '1\n'),
                      ('wait/send', sel_re, '4\n'),
                      ('wait', re.compile('STATE CODES FOR THE U\.S\.\s*-+')),
                      ('read', re.compile('CITY FORECAST MENU')),
                      ('wait/send', sel_re, 'X\n'), ('quit', )), host, port)

    return str.join('\n', [p.strip() for p in out[0].split('\n')])


# }}

# {{ run_program(pgm, host, port)


def run_program(pgm, host, port):
    """Back end for communicating with the weather engine."""

    conn = socket(AF_INET, SOCK_STREAM, 0)
    conn.connect((host, port))
    data = ['']

    def wait_for(expr, resume=None, skip=True):
        global debug

        match = expr.search(data[0])

        while not match:
            if resume:
                m = resume[0].search(data[0])
                if m:
                    data[0] = data[0][:m.start()] + data[0][m.end():]
                    send_cmd(resume[1])

            s = conn.recv(4096).replace('\r', '')
            if not s:
                raise EOFError("Unexpected EOF while waiting for `%s'" %
                               expr.pattern)

            data[0] += s
            match = expr.search(data[0])

        if skip:
            out = data[0][:match.start()]
        else:
            out = data[0][:match.end()]

        data[0] = data[0][match.end():]

        if debug:
            print >> sys.stderr, "<< %s <<[end]" % \
                  out.replace('\n', '\\n')

        return out

    def send_cmd(cmd):
        global debug

        if debug:
            print >> sys.stderr, ">> %s" % cmd

        conn.send(cmd.replace('\n', '\r\n'))

    out = []
    for inst in pgm:
        if inst[0] == 'send':
            send_cmd(inst[1])
        elif inst[0] == 'wait':
            wait_for(inst[1])
        elif inst[0] == 'wait/send':
            wait_for(inst[1])
            send_cmd(inst[2])
        elif inst[0] == 'read':
            t = wait_for(inst[1])
            out.append(t)
        elif inst[0] == 'read/resume':
            t = wait_for(inst[1], (inst[2], inst[3]))
            out.append(t)
        elif inst[0] == 'quit':
            conn.close()
            break
        else:
            raise ValueError("Unknown instruction: %s" % (inst, ))

    return [t.strip() for t in out]


# }}

# {{ parse_weather(data)


def parse_weather(data):
    """Parse the raw output of NWS reports, returning a dictionary of
    relevant results.  You can pass the resulting dictionary to the
    format_info() function to get a nicely human-readable string."""

    lines = iter(data.split('\n'))

    # Hack apart the fixed portions of the format
    info = {}
    match = head_re.match(lines.next())
    if match:
        info['load-time'] = match.group(1)
        info['load-date'] = match.group(2)
        info['location1'] = match.group(3)

    # See if there are vital statistics at the top of the report
    # (Temperature, pressure, etc.)
    fields = lines.next().split()
    field_info = []
    for f in fields:
        match = field_re.match(f)
        if match:
            field_info.append({'name': match.group(1), 'unit': match.group(2)})

    if field_info:
        info['fields'] = field_info

    lines.next()  # Skip separator line
    fields = lines.next().strip()
    info['data'] = re.split('\s{2,}', fields)
    if field_info:
        for (pos, data) in enumerate(info['data']):
            info['fields'][pos]['data'] = data
        del info['data']

    match = None
    while not match:
        try:
            line = lines.next()
        except StopIteration:
            raise EOFError("Unexpected end-of-input before location found")

        match = loc_re.match(line)
        if match:
            info['location2'] = match.group(1)
            break

    # Figure out when the report was issued, and turn that into seconds.
    match = time_re.match(lines.next())
    if match:
        h = int(match.group(1))
        t = '%02d:%02d %s %s %s %02d %04d' % \
            ( (h / 100), (h % 100),
              match.group(2).lower(),
              match.group(4).capitalize(),
              match.group(5).capitalize(),
              int(match.group(6)),
              int(match.group(7)) )

        info['issued'] = time.mktime(time.strptime(t, time_format))

    # Read the weather reports
    info['reports'] = []

    # Skip junk until we start seeing real reports
    while True:
        try:
            line = lines.next()
            if cast_re.match(line):
                break
        except StopIteration:
            return info

    # Read until we stop seeing reports
    data = {}
    while True:
        if re.match('\s*$', line) or end_re.match(line):
            break

        match = cast_re.match(line)
        if match:
            if data:
                info['reports'].append(data)
                data = {}

            data['when'] = match.group(1)
            data['summary'] = match.group(2).strip().replace('...', ', ')
        elif line:
            data['summary'] += ' ' + line.strip().replace('...', ', ')

        try:
            line = lines.next()
        except StopIteration:
            break

    if data:
        info['reports'].append(data)

    # Pick up any extra stuff at the end (warnings, etc.)
    data = [
        re.sub('^\.\.\.', '', ln.rstrip()).replace('...', ', ') for ln in lines
    ]
    data = str.join('\n', data).rstrip()
    if data:
        info['extra'] = data

    return info


# }}

# {{ format_info(info)


def format_info(info):
    """Format an info dictionary returned by parse_weather(), and
    return a string of nicely human-readable output."""

    # -- Print out a summary in human-readable format
    out = ''
    out += "Weather report for: %s\n" % info['location1']
    out += "Report issued:      %s\n\n" % \
           time.strftime('%I:%M%p on %A, %B %e, %Y',
                         time.localtime(info['issued']))
    if info.has_key('fields'):
        out += "Vital statistics:\n"
        for f in info['fields']:
            msg = ' * %s' % f['name'].capitalize()
            if f['unit']:
                msg += ' (%s)' % f['unit']

            msg += ':'
            if len(msg) < stat_width:
                msg += ' ' * (stat_width - len(msg))

            out += msg
            out += f['data'] + '\n'

    wrapper = textwrap.TextWrapper(width=72,
                                   subsequent_indent='   ',
                                   fix_sentence_endings=True)

    for r in info['reports']:
        out += "\n - %s\n" % r['when']
        out += "   %s\n" % wrapper.fill(r['summary'])

    if info.has_key('extra'):
        wrapper = textwrap.TextWrapper(width=72, fix_sentence_endings=True)

        out += "\n-- Other information:"
        for msg in re.split('\n{2,}', info['extra']):
            if re.match('\s*[*&]+', msg):
                out += '\n' + msg + '\n'
            else:
                out += '\n' + wrapper.fill(msg) + '\n'

    return out


# }}

# {{ get_weather(station, host, port)


def get_weather(station, host=default_host, port=default_port):
    """A high-level interface to the other functions in this library;
    returns a formatted weather report for the specified weather
    station."""

    return format_info(parse_weather(fetch_weather(station, host, port)[0]))


# }}

# {{ get_state_codes(host, port)


def get_state_codes(host=default_host, port=default_port):
    """Return a dictionary of all the state codes."""

    raw = fetch_state_codes(host, port)
    expr = re.compile('([A-Z]{2}) (\w+(?: \w+)*)')

    out = {}
    for match in expr.finditer(raw):
        out[match.group(1)] = match.group(2)

    return out


# }}

# {{ get_city_codes(state, host, port)


def get_city_codes(state, host=default_host, port=default_port):
    """Return a dictionary of all the city codes for a given state."""

    raw = fetch_city_codes(state, host, port)
    expr = re.compile('([A-Z]{2})\s+([A-Z]{3})\s+(.+)$')

    out = {}
    for line in raw.split('\n'):
        match = expr.match(line)
        if match:
            out[match.group(2)] = match.group(3)

    return out


# }}

__all__ = ('get_weather', 'get_state_codes', 'get_city_codes', 'format_info',
           'parse_weather')

# Here there be dragons
