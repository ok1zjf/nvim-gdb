"""Plugin entry point."""

# pylint: disable=broad-except
import sys, os
import re
from contextlib import contextmanager
import logging
import logging.config
from typing import Dict
import pynvim   # type: ignore
from gdb.common import BaseCommon, Common
from gdb.app import App
from gdb.config import Config
from gdb.logger import LOGGING_CONFIG
from gdb.efmmgr import EfmMgr

import neovim

@pynvim.plugin
class Gdb(Common):
    """Plugin implementation."""

    def __init__(self, vim):
        """ctor."""
        logging.config.dictConfig(LOGGING_CONFIG)
        # self.logger.info("Plugin initialized vim=%x", vim)
        common = BaseCommon(vim, None)
        super().__init__(common)
        self.apps: Dict[int, App] = {}
        self.ansi_escaper = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
        self.efmmgr = None
        self.breakpoints = {}

    def _get_app(self) -> int:
        return self.apps.get(self.vim.current.tabpage.handle, None)

    @pynvim.function('GdbInit', sync=True)
    def gdb_init(self, args):
        """Handle the command GdbInit."""
        # Prepare configuration: keymaps, hooks, parameters etc.
        # self.logger.info("***** GdbInit vim=%s", str(vim))
        common = BaseCommon(self.vim, Config(self))
        if not self.apps:
            self.efmmgr = EfmMgr(common)
        app = App(common, self.efmmgr, *args)
        self.apps[self.vim.current.tabpage.handle] = app
        app.start()
        if len(self.apps) == 1:
            # Initialize the UI commands, autocommands etc
            self.vim.call("nvimgdb#GlobalInit")
        # self.logger.info("@@@@ GdbInit vim=%s  %s", str(vim), str(self.vim))

    @contextmanager
    def _saved_hidden(self):
        # Prevent "ghost" [noname] buffers when leaving the debugger
        # and 'hidden' is on
        hidden = self.vim.eval("&hidden")
        if hidden:
            self.vim.command("set nohidden")
        yield
        # sets hidden back to user default
        if hidden:
            self.vim.command("set hidden")

    @pynvim.function('GdbCleanup', sync=True)
    def gdb_cleanup(self, args):
        """Handle the command GdbCleanup."""
        tab = int(args[0])
        self.logger.info("Cleanup tab=%d", tab)
        try:
            app = self.apps.pop(tab, None)
            if app:
                with self._saved_hidden():
                    if len(self.apps) == 0:
                        # Cleanup commands, autocommands etc
                        self.vim.call("nvimgdb#GlobalCleanup")
                        self.efmmgr.cleanup()
                        self.efmmgr = None
                    app.cleanup(tab)
                # TabEnter isn't fired automatically when a tab is closed
                self.gdb_handle_event(["on_tab_enter"])
        except Exception:
            err = 'Error: {}'.format(sys.exc_info()[0])
            self.logger.exception("FIXME GdbCleanup Exception. Error:",err)

    @pynvim.function('GdbHandleEvent', sync=True)
    def gdb_handle_event(self, args):
        """Handle the command GdbHandleEvent."""
        self.logger.info("GdbHandleEvent %s", ' '.join(args))
        try:
            app = self._get_app()
            if app:
                handler = getattr(app, args[0])
                handler()
        except Exception:
            self.logger.exception("GdbHandleEvent Exception")

    @pynvim.function('GdbHandleTabClosed', sync=True)
    def gdb_handle_tab_closed(self, _):
        """Handle the function GdbHandleTabClosed."""
        self.logger.info("GdbHandleTabClosed")
        active_tabs = {t.handle for t in self.vim.tabpages}
        managed_tabs = {t for t, _ in self.apps.items()}
        closed_tabs = managed_tabs.difference(active_tabs)
        for tab in closed_tabs:
            self.gdb_cleanup([tab])

    @pynvim.function('GdbHandleVimLeavePre', sync=True)
    def gdb_handle_vim_leave_pre(self, _):
        """Handle function GdbHandleVimLeavePre."""
        self.logger.info("GdbHandleVimLeavePre")
        # Make sure a copy of the list is made.
        for tab in [t for t, _ in self.apps.items()]:
            self.gdb_cleanup([tab])

    @pynvim.function('GdbSend', sync=True)
    def gdb_send(self, args):
        """Handle command GdbSend."""
        try:
            app = self._get_app()
            if app:
                app.send(*args)
        except Exception:
            self.logger.exception("GdbSend Exception")

    @pynvim.function('GdbBreakpointToggle', sync=True)
    def gdb_breakpoint_toggle(self, _):
        """Handle command GdbBreakpointToggle."""
        try:
            app = self._get_app()
            self.logger.info(f"GdbBreakpointToggle Toggle. app: {app}")
            if app:
                app.breakpoint_toggle()
        except Exception:
            self.logger.exception('GdbBreakpointToggle Exception')

    @pynvim.function('GdbBreakpointClearAll', sync=True)
    def gdb_breakpoint_clear_all(self, _):
        """Handle command GdbBreakpointClearAll."""
        try:
            app = self._get_app()
            if app:
                app.breakpoint_clear_all()
        except Exception:
            self.logger.exception('GdbBreakpointClearAll Exception')

    @pynvim.function('GdbParserFeed')
    def gdb_parser_feed(self, args):
        """Handle command GdbParserFeed."""
        try:
            tab = args[0]
            app = self.apps.get(tab, None)
            if app:
                content = args[1]
                for i, ele in enumerate(content):
                    content[i] = self.ansi_escaper.sub('', ele)
                app.parser.feed(content)
        except Exception:
            self.logger.exception('GdbParserFeed Exception')

    @pynvim.function('GdbParserDelayElapsed')
    def gdb_parser_delay_elapsed(self, args):
        """Handle command GdbParserDelayElapsed."""
        try:
            tab = args[0]
            app = self.apps.get(tab, None)
            if app:
                app.parser.delay_elapsed(args[1])
        except Exception:
            self.logger.exception('GdbParserDelayElapsed Exception')

    @pynvim.function('GdbCallAsync')
    def gdb_call_async(self, args):
        """Handle command GdbCallAsync."""
        try:
            obj = self._get_app()
            if obj:
                for name in args[0].split('.'):
                    obj = getattr(obj, name)
                obj(*args[1:])
        except Exception:
            self.logger.exception('GdbCallAsync Exception')

    @pynvim.function('GdbCall', sync=True)
    def gdb_call(self, args):
        """Make a custom call to the App.

        Reads a period separated list of words and invokes the corresponding
        method on the `App` class.
            e.g.
                self.gdb_call(['custom_command'] + args)
                  maps to
                self.app.custom_command(args)
        """
        try:
            obj = self._get_app()
            # print('obj:', obj)
            # print('args:',args)
            self.logger.info("GdbCall args=%s", args)
            if obj:
                for name in args[0].split('.'):
                    obj = getattr(obj, name)
                if callable(obj):
                    self.logger.info("GdbCall return0=%s", obj)
                    return obj(*args[1:])
                self.logger.info("GdbCall return1=%s", obj)
                return obj
        except Exception:
            self.logger.exception('GdbCall Exception')
        return None

    @pynvim.function('GdbCustomCommand', sync=True)
    def gdb_custom_command(self, args):
        """Handle command GdbCustomCommand."""
        return self.gdb_call(["custom_command"] + args)

    @pynvim.function('GdbCreateWatch', sync=True)
    def gdb_create_watch(self, args):
        """Handle command GdbCreateWatch."""
        return self.gdb_call(["create_watch"] + args)

    @pynvim.function('GdbShowLocals', sync=True)
    def gdb_show_locals(self, _):
        return self.gdb_call(["show_locals", "none"])

    @pynvim.function('GdbSaveBreaks', sync=True)
    def gdb_save_breaks(self, _):
        """Handle command GdbSaveBreaks."""
        obj = self._get_app()
        if obj.backend_name == 'pdb':
            msg = self.gdb_call(["custom_command", "b"])
            lines = msg.split('\n')
            i = 0

            breaks = []
            while i < len(lines):
                line = lines[i]
                ts = line.split(' ')
                ts = [ v.strip() for v in ts if v.strip() != '']
                if len(ts)<3:
                    break

                if ts[1] == 'breakpoint':
                    b = 'break '+' '.join(ts[5:])
                    breaks.append(b)

                if ' '.join(ts[:3]) == 'stop only if':
                    cond = ' '.join(ts[3:])
                    b = breaks[-1]+', '+cond
                    breaks[-1] = b

                i += 1

            with open(".pdbrc", "wt") as pdbrc:
                pdbrc.write('\n'.join(breaks))
            return 'Breakpoints saved. Num: '+str(len(breaks)) 

        if obj.backend_name == 'gdb':
            msg = self.gdb_call(["custom_command", "save breakpoints breaks"])
            return msg

        return None


    @pynvim.function('GdbTestPeek', sync=True)
    def gdb_test_peek(self, args):
        """Handle command GdbTestPeek."""
        try:
            obj = self._get_app()
            if obj:
                for i, arg in enumerate(args):
                    obj = getattr(obj, arg)
                    if callable(obj):
                        return obj(*args[i+1:])
                return obj
        except Exception:
            self.logger.exception('GdbTestPeek Exception')
        return None

    @pynvim.function('GdbTestPeekConfig', sync=True)
    def gdb_test_peek_config(self, _):
        """Handle command GdbTestPeekConfig."""
        try:
            app = self._get_app()
            if app:
                config = dict(app.config.config)
                for key, val in config.items():
                    if callable(val):
                        config[key] = str(val)
                return config
        except Exception:
            self.logger.exception('GdbTestPeekConfig Exception')
        return None


#===============================================================
    # @property
    def cbname(self):
        """cbname
        returns the current buffer's name attribute
        """
        return self.vim.current.buffer.name

    def load_breakpoints(self):
        # Load breakpoints from file
        if not os.path.isfile('.pdbrc'):
            return

        self.breakpoints = {}
        with open('.pdbrc', 'rt') as f:
            for line in f:
                self.logger.info("line: %s", line)
                line = line.strip()
                toks = line.split(' ')
                if len(toks) < 2 and toks[0].strip() != 'break':
                    continue
                toks = ' '.join(toks[1:])
                break_name = toks
                toks = toks.split(':')
                if len(toks) < 2:
                    continue
                filename = ' '.join(toks[:-1])
                line_nr = int(toks[-1])

                self.breakpoints[break_name] = [filename, line_nr]
        return

    def save_breakpoints(self):
        breaks = []
        for n, v in self.breakpoints.items():
            b = 'break '+n
            breaks.append(b)

        with open(".pdbrc", "wt") as pdbrc:
            pdbrc.write('\n'.join(breaks))
        return

    @neovim.command("GdbLoadBreakpoints", sync=False)
    def set_breakpoints_cmd(self, buffname=None):
        if not buffname:
            buffname = self.cbname()
        
        self.load_breakpoints()
        self.logger.info("line: %s", self.breakpoints)
        # remove all breakpoints
        self.vim.command('sign unplace * file={}'.format(buffname))
        # show breakpoints
        for n, v in self.breakpoints.items():
            filename, line_nr = v
            if buffname == filename:
                self.logger.info("Setting Break: %s   %s", buffname, line_nr)
                sign_id = 10 * line_nr
                self.vim.command('sign place {} line={} name={} file={}'.format(
                    sign_id, line_nr, self.vim.eval('g:gdb_sign_name'), buffname)
                )
        return

    @neovim.command("GdbABreak", sync=False)
    def toggle_breakpoint_cmd(self, buffname=None):
        if not buffname:
            buffname = self.cbname()

        row = self.vim.current.window.cursor[0]
        break_name = buffname+":"+str(row)
        # self.logger.info("Break toggle %s   %s", buffname, row)

        sign_id = 10 * row
        if break_name in self.breakpoints:
            self.logger.info("Removing Break: %s   %s", buffname, row)
            del self.breakpoints[break_name]
            self.vim.command('sign unplace {} file={}'.format(sign_id, buffname))
        else:
            self.logger.info("Setting Break: %s   %s", buffname, row)
            self.breakpoints[break_name] = row
            self.vim.command('sign place {} line={} name={} file={}'.format(
                sign_id, row, self.vim.eval('g:gdb_sign_name'), buffname)
            )

        self.save_breakpoints()
        self.gdb_breakpoint_toggle(None)
        return


