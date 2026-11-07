"""Render report figures (PNG) with matplotlib. Run: python report/make_figures.py"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent / 'figures'
NAVY, LINE, TEXT = '#1B3A57', '#6B7F95', '#1D2330'
FILL = {'blue': '#E8EEF6', 'green': '#E6F0EA', 'yellow': '#FFF5E0', 'purple': '#EEEAF5', 'red': '#FBE9E9'}
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})


def box(ax, x, y, w, h, text, fill='blue', dashed=False, size=10, bold_first=True):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.08',
                                fc=FILL[fill], ec=LINE, lw=1.1, ls='--' if dashed else '-'))
    lines = text.split('\n')
    n = len(lines)
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h / 2 + (n - 1) * 0.14 - i * 0.28, line, ha='center', va='center',
                fontsize=size, color=TEXT, weight='bold' if (i == 0 and bold_first) else 'normal')


def arrow(ax, x1, y1, x2, y2, label=None, dashed=False):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='-|>', color=LINE, lw=1.2, ls='--' if dashed else '-'))
    if label:
        if abs(y1 - y2) < 0.01:  # horizontal: label above the line
            ax.text((x1 + x2) / 2, y1 + 0.12, label, fontsize=8.5, color=LINE, ha='center', va='bottom')
        else:  # vertical/diagonal: label to the right of the midpoint
            ax.text((x1 + x2) / 2 + 0.1, (y1 + y2) / 2, label, fontsize=8.5, color=LINE, va='center')


def figure_architecture():
    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis('off')
    ax.text(0.1, 5.75, 'A4 slice architecture (all local, 127.0.0.1)', fontsize=13, weight='bold', color=NAVY)
    box(ax, 0.3, 4.3, 3.6, 1.0, 'Browser UI\nindex.html, app.js (CSP, no inline JS)')
    box(ax, 5.0, 4.3, 4.6, 1.0, 'Local HTTP server  server.py\nroutes, 4 KB limit, JSON, security headers')
    box(ax, 5.0, 2.55, 4.6, 1.25, 'Application service  service.py\nauth, ownership, idempotency,\nexpected_version, source, time rules', fill='green')
    box(ax, 0.3, 2.55, 3.6, 1.25, 'A2 domain model  domain.py\nunchanged; parse_deadline,\nDecision enum', fill='green')
    box(ax, 5.0, 0.4, 4.6, 1.5, 'SQLite file  local/deadlines.db\n8 tables, 5 guard triggers\n(version, owner, transitions,\nappend-only history)', fill='purple')
    box(ax, 0.3, 0.6, 3.6, 1.1, 'Export adapter  ics.py\nVTODO .ics, read-only copy', fill='yellow')
    arrow(ax, 3.9, 4.8, 5.0, 4.8, 'HTTP\n+ token')
    arrow(ax, 7.3, 4.3, 7.3, 3.8)
    arrow(ax, 5.0, 3.15, 3.9, 3.15, 'rules')
    arrow(ax, 7.3, 2.55, 7.3, 1.9, 'BEGIN IMMEDIATE')
    arrow(ax, 5.0, 2.7, 3.9, 1.4, 'export')
    fig.tight_layout()
    fig.savefig(OUT / 'fig1-architecture.png', dpi=200)
    plt.close(fig)


def figure_write_path():
    steps = [
        ('Read body (bounded)', '> 4096 B', '413', 'blue'),
        ('Authenticate bearer token', 'missing / invalid', '401', 'blue'),
        ('Feature flag on?', 'off', '503', 'blue'),
        ('Validate JSON, key, decision, version', 'malformed', '400 / 415', 'blue'),
        ('BEGIN IMMEDIATE; idempotency lookup', 'same key', 'replay / 422', 'green'),
        ('Owner of candidate?', 'no / unknown', '404', 'green'),
        ('Candidate state', 'not pending', '409 (or 200 already)', 'green'),
        ('expected_version = current?', 'no', '409 STALE', 'green'),
        ('REJECT -> close candidate', 'deadline unchanged', '200', 'yellow'),
        ('base_version = current?', 'no', '409 OUTDATED', 'green'),
        ('Verified official source? Valid zone?', 'no', '422', 'green'),
        ('history +1 -> version +1 -> APPLIED; COMMIT', 'success', '200', 'purple'),
    ]
    fig, ax = plt.subplots(figsize=(9.2, 7.6))
    n = len(steps)
    ax.set_xlim(0, 10); ax.set_ylim(0, n * 0.62 + 0.7); ax.axis('off')
    ax.text(0.1, n * 0.62 + 0.4, 'Decision request: order of server-side checks', fontsize=13, weight='bold', color=NAVY)
    for i, (label, cond, outcome, fill) in enumerate(steps):
        y = (n - 1 - i) * 0.62 + 0.1
        box(ax, 0.2, y, 5.6, 0.46, label, fill=fill, size=9.5, bold_first=False)
        ax.text(6.85, y + 0.27, cond, fontsize=8, color=LINE, ha='center', va='bottom')
        ok = outcome.startswith('200') or outcome.startswith('replay')
        ax.add_patch(FancyBboxPatch((7.9, y + 0.05), 1.9, 0.36, boxstyle='round,pad=0.02,rounding_size=0.06',
                                    fc=FILL['green'] if ok else FILL['red'], ec=LINE, lw=0.8))
        ax.text(8.85, y + 0.23, outcome, fontsize=8.5, ha='center', va='center', color=TEXT)
        ax.annotate('', xy=(7.9, y + 0.23), xytext=(5.8, y + 0.23),
                    arrowprops=dict(arrowstyle='-|>', color='#B0BAC6', lw=0.8))
        if i < n - 1:
            ax.annotate('', xy=(3.0, y - 0.16), xytext=(3.0, y),
                        arrowprops=dict(arrowstyle='-|>', color=LINE, lw=1.0))
    fig.tight_layout()
    fig.savefig(OUT / 'fig2-write-path.png', dpi=200)
    plt.close(fig)


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    figure_architecture()
    figure_write_path()
    print('figures written to', OUT)
