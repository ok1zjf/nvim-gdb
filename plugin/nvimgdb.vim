if exists("g:loaded_nvimgdb") || !has("nvim")
    finish
endif
let g:loaded_nvimgdb = 1

function! s:Spawn(backend, proxy_cmd, client_cmd)
  "Expand words in the client_cmd to support %, <word> etc
  "let cmd=a:client_cmd
  let cmd = join(map(split(a:client_cmd, "/"), {k, v -> expand(v)}), "/")
  "let cmd = join(map(split(a:client_cmd), {k, v -> expand(v)}))
  call GdbInit(a:backend, a:proxy_cmd, cmd)
endfunction

command! -nargs=1 -complete=shellcmd GdbStart call s:Spawn('gdb', 'gdb_wrap.sh', <q-args>)
command! -nargs=1 -complete=shellcmd GdbStartLLDB call s:Spawn('lldb', 'lldb_wrap.sh', <q-args>)
command! -nargs=1 -complete=shellcmd GdbStartPDB call s:Spawn('pdb', 'pdb_proxy.py', <q-args>)
command! -nargs=1 -complete=shellcmd GdbStartBashDB call s:Spawn('bashdb', 'bashdb_proxy.py', <q-args>)

if !exists('g:nvimgdb_disable_start_keymaps') || !g:nvimgdb_disable_start_keymaps
  nnoremap <leader>dd :GdbStart gdb -ex "source breaks" -ex "start" -q build/%:r
  nnoremap <leader>dl :GdbStartLLDB lldb a.out
  nnoremap <leader>dp :GdbStartPDB python3 -m pdb ./%
  nnoremap <leader>db :GdbStartBashDB bashdb main.sh
endif

" Part of the support for offline breakpoints
let g:gdb_highlight_group='debug'
let g:gdb_breakpoint_symbol='*'
let g:gdb_sign_name='gdbbp'
execute 'sign' 'define' g:gdb_sign_name 'text='.g:gdb_breakpoint_symbol 'texthl='.g:gdb_highlight_group


