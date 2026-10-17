# Design

## Context

See proposal.md for why. The current state, in procd 2026.09.26 (a6f9ffd4), the same in upstream's tree:
- `system.c`'s `validate_firmware_image_call` forks `/usr/libexec/validate_firmware_image <path>`, with its stdout on a pipe, and `vjson_parse` reads the pipe with blocking `read()` until a complete JSON object or EOF. The result goes into the file's global `blob_buf b`, and an error into a static buffer of `vjson_error`.
- Two ubus methods of the `system` object call it in the handler itself: `validate_firmware_image`, which replies with the result, and `sysupgrade`, which checks the result, stops all services and replaces procd with `upgraded`.
- `sysupgrade` (the command) calls both: the validation first, then `system sysupgrade`, which validates again.
- The validation script opens the image several times: fwtool's signature and metadata checks, then `platform_check_image`, which on an A/B system lists the image's tar members twice.
- procd feeds the watchdog from a uloop timer every 5 s, with a 30 s timeout. While a handler blocks, the timer does not run.
- procd's ubus context is created once and reconnected in place (`ubus.c`), so a pointer to it stays valid.
- The evidence (emulator-watchdog-time's measurements, on the VM, R4S, `firmware/test_ab_upgrade.py` with the session on four host cores and `stress-ng --cpu 4` on them):
  - seven resets in a run, each logged by QEMU as `watchdog_perform_action`;
  - a sampler of QEMU's threads: the emulated cores ran at 84 to 90 % of a host core together in the 35 s before each reset, none in uninterruptible I/O, and the main loop idle: no freeze of the guest;
  - a monitor in the guest, every 2 s on the console: procd in `anon_pipe_read`, with no CPU time, for the last 22 to 28 s before each reset, the monitor itself on time throughout.

## Goals / Non-Goals

**Goals:**
- procd's main loop never waits for a validation script: the watchdog, ubus and service supervision go on.
- Both methods answer as before, with the same results and errors, once the validation has ended.

**Non-Goals:**
- A time limit on the validation: a validation that never ends never answered before either; now procd goes on meanwhile.
- Making the validation faster.
- Changing what `validate_firmware_image` checks.

## Decisions

### D1. The validation runs in procd's event loop

A `struct validation` holds what one validation needs: the pipe's read end as a `uloop_fd`, a `json_tokener`, the count of bytes read, the parse state, its own `blob_buf` for the result and error buffer, the deferred ubus request, a copy of the request's message, and a completion callback.
- Starting it forks the script as before, with the pipe's ends close-on-exec in procd. procd sets the read end non-blocking and adds it to the event loop, defers the ubus request (`ubus_defer_request`), and returns.
- The read callback reads what is there, feeds the tokenizer, and ends the validation on a complete JSON object, an error, or EOF, with the same messages as before ("no JSON input", "incomplete JSON input", "read() failed"). It then removes and closes the fd and calls the completion callback, which answers the deferred request and frees the validation.
- The child is reaped as before: uloop reaps every child of procd.

Alternatives considered:
- **Ping the watchdog while reading**: the watchdog survives, but ubus and service supervision still wait; and procd's main loop would gain a second place that feeds the watchdog.
- **A thread for the validation**: procd is single-threaded throughout, and the event loop already offers what the job needs.
- **A time limit**: the old code had none, and a limit is a policy for upstream to choose, not a fix.

### D2. The two methods as completions

- `validate_firmware_image`'s completion replies with the validation's result and completes the request, with `UBUS_STATUS_OK`, or `UBUS_STATUS_UNKNOWN_ERROR` when the validation failed, as before.
- `sysupgrade` copies its message (`blob_memdup`) before it defers. Its completion takes the remainder of today's handler unchanged: the checks of the result with their error replies and statuses, then `service_stop_all()` and `sysupgrade_exec_upgraded()`. If that returns, it completes the request with `UBUS_STATUS_UNKNOWN_ERROR`.
- The result no longer lives in the global `b`, and the error message no longer in a static buffer, so two validations at once do not overwrite each other's.

### D3. The patch

`patches/openwrt/0039-procd-validate-firmware-images-without-blocking.patch` adds `package/system/procd/patches/100-system-validate-firmware-images-without-blocking-the-main-loop.patch` and sets procd's `PKG_RELEASE` to 3. The inner patch's message is written for procd upstream. The outer patch carries `Upstream-Status: Pending`, and `docs/patches.md` has its write-up.

### D4. The test

`firmware/ab-upgrade` "A validation slower than the watchdog", in `tests/firmware/test_ab_upgrade.py`:
- The image path is a FIFO on the router (`mkfifo`). A FIFO's open waits for a writer, so every read of the image by the script waits, on any host, for as long as the test likes.
- The test starts `ubus -t 300 call system validate_firmware_image` on it, detached, and writes its output and exit status to a file.
- For 45 s, more than procd's 30 s timeout, `ubus call system board` must answer within 10 s every 5 s. Then the router's boot ID must be unchanged and `qemu.log` must hold no new watchdog action.
- The test then ends every process that has the FIFO open, until the call has returned, so each check that waits on the image fails. Closing a writer's end would not do: fwtool opens the image read-write, and a reader that is itself a writer never sees the end of a FIFO's input. The validation must end, and the call must return the result: an invalid image.

Without the patch, the first `system board` call after the validation's start times out, and the watchdog resets the router after 30 s.

### D5. Verification

- The test without the patch fails (once, on the R4S), and passes with it on both boards.
- The CI-like reproduction on the R4S (`firmware/test_ab_upgrade.py` on four host cores with `stress-ng --cpu 4`): no watchdog action outside the tests that cause one, and every test passing, twice.
- The full system tests on both boards, then CI.

## Risks / Trade-offs

- [A client that relied on the validation blocking procd] → None does: the reply comes when it came before, only procd does not stop meanwhile.
- [A validation that never ends keeps its request and fd open] → As before it kept procd itself; the ubus client times out on its side as before, and the fd closes when the script ends.
- [ubus reconnects during a validation] → The context is the same object after a reconnect; the reply goes to a peer that is gone, which ubus drops.
- [Upstream prefers another form] → The patch is Pending; the write-up names the alternatives.
