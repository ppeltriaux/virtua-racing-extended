-- Weather Task 6J (the join): the make-up of a pass's time with every module of the storm on. One line per pass of the main loop,
-- written at the exit of the wait that ends it (as storm_log.lua's S lines: the same frame):
--   M <frame> <busy us: the pass's start (the wait's exit) to its end (the next wait's first read)> <the scenery routine's return:
--     us from the pass's start to the storm stub's last read of SWITCH / STATE before the carrier's body (after the routine: a read
--     of 0x520000..1 from VR_MAKEUP_STUB "lo,hi" hex; the stub's reads before the routine come earlier), -1 when none> <the carrier's body: us from the
--     pass's start to its show counter's write (VR_MAKEUP_NSHOW hex), -1 when none> <for each module of VR_MAKEUP_CODES, in its
--     order: us from the pass's start to the module's first guard test (a read of the vblank count 0x500501 from its code), -1 when
--     none> <the wet handling's hook calls this pass> <their time, us> <the vblank count's move: us from the pass's start, -1
--     when it did not move in the pass's work> <the pc of the storm's last guard test before the move, hex (the unit in flight began
--     there), 0 when none> <the trip: us from the pass's start to the first guard test of the storm's code that read the count moved,
--     -1 when none> <its pc, hex, 0 when none> <1 when this pass's late state was forced (below), else 0>
-- The tail of a pass: from the trip to the pass's end. VR_MAKEUP_FORCE_LATE=N (a measurement run only): on every N-th show pass the
-- count is written 1 at the carrier body's show-counter write, so every module's first guard test finds the pass late: the trip is
-- the first module's first test and the tail runs through every module's late path (the worst case over the registry order); the
-- game's wait then ends at once, so that pass's frame is short and the run's later passes are not the plain run's.
-- A module's time is then from its first test to the next module's (every frame routine tests the guard first: the carrier's
-- contract); the last module's runs to the pass's end with the game's tail after the scenery call. The handling's calls (its hooks
-- in the game's physics code, outside the scenery call): from each stub's first test (a read of the weather byte 0x502296 from the
-- stubs' block, VR_MAKEUP_STUBS "lo,hi" hex) to the routine's last access of the handling's cells (VR_MAKEUP_HCELLS "lo,hi" hex)
-- before the next call or the pass's end; a lower bound by the few instructions of each exit (a jump back, about 1 us).
-- The join's round 2 (J1, the sound's trigger exempt from the guard): with VR_MAKEUP_SCELLS "lo,hi" (hex: the sound's cells) each
-- M line ends with one more field: us from the pass's start to the pass's last access (read or write) of that range, -1 when none:
-- the trigger's last access before its return (on an idle pass the read of `seen`, on a sending pass the count of the word sent),
-- so the trigger's cost is that less the sound's first guard test, short by its return's few instructions.
-- Env: VR_MAKEUP_LOG (path), VR_MAKEUP_CODES "name:lo:hi[,...]" (hex), VR_MAKEUP_NSHOW (hex), VR_MAKEUP_STUB, VR_MAKEUP_STUBS,
-- VR_MAKEUP_HCELLS, VR_MAKEUP_FORCE_LATE, VR_MAKEUP_SCELLS.
-- Loaded with VR_EXTRA_LUA. The last line is "END".
local path = assert(os.getenv("VR_MAKEUP_LOG"), "storm_makeup.lua: VR_MAKEUP_LOG is not set")
local out = assert(io.open(path, "w"))
local cpu = manager.machine.devices[":maincpu"]
local prog = cpu.spaces["program"]
local pcst = cpu.state["PC"]
local codes = {}
for name, lo, hi in string.gmatch(os.getenv("VR_MAKEUP_CODES") or "", "([%w_]+):(%x+):(%x+)") do
  codes[#codes + 1] = {name, tonumber(lo, 16), tonumber(hi, 16)}
end
assert(#codes > 0, "storm_makeup.lua: VR_MAKEUP_CODES is empty")
local nshow = tonumber(assert(os.getenv("VR_MAKEUP_NSHOW")), 16)
local tlo, thi = string.match(os.getenv("VR_MAKEUP_STUB") or "0,0", "(%x+),(%x+)")
tlo, thi = tonumber(tlo, 16), tonumber(thi, 16)
local slo, shi = string.match(os.getenv("VR_MAKEUP_STUBS") or "0,0", "(%x+),(%x+)")
local hlo, hhi = string.match(os.getenv("VR_MAKEUP_HCELLS") or "0,0", "(%x+),(%x+)")
slo, shi, hlo, hhi = tonumber(slo, 16), tonumber(shi, 16), tonumber(hlo, 16), tonumber(hhi, 16)
if hhi > hlo then hlo, hhi = hlo & ~3, (hhi - 1) | 3 end    -- [lo, hi) as the taps' inclusive, whole-word range
local function now() return manager.machine.time:as_double() end
local sclo, schi = string.match(os.getenv("VR_MAKEUP_SCELLS") or "0,0", "(%x+),(%x+)")
sclo, schi = tonumber(sclo, 16), tonumber(schi, 16)
local s_last = nil
local force_every = tonumber(os.getenv("VR_MAKEUP_FORCE_LATE") or "")
local shows = 0
local t_move, unit_pc, last_pc, trip, trip_pc, forced = nil, 0, 0, nil, 0, 0
local frame = 0
emu.register_frame_done(function() frame = frame + 1 end)
local t0, body, first, in_wait, t_end, ret = nil, nil, {}, false, nil, nil
local hcalls, hus, h_in, h_last = 0, 0.0, nil, nil
local function close_call()
  if h_in then hus = hus + ((h_last or h_in) - h_in) * 1e6; h_in, h_last = nil, nil end
end
_G.vr_makeup_vbl_r = prog:install_read_tap(0x500500, 0x500501, "vr_makeup_vbl_r", function(offset, data, mask)
  if (mask & 0xff00) == 0 or not t0 then return end
  local pc = pcst.value
  if not in_wait and pc >= 0xfe13db and pc <= 0xfe13f3 then in_wait = true; t_end = now(); close_call(); return end
  for k, c in ipairs(codes) do
    if pc >= c[2] and pc < c[3] then
      if not first[k] then first[k] = now() end
      if ((data >> 8) & 0xff) ~= 0 then
        if not trip then trip, trip_pc = now(), pc end
      elseif not t_move then last_pc = pc end
    end
  end
end)
_G.vr_makeup_vbl_w = prog:install_write_tap(0x500500, 0x500501, "vr_makeup_vbl_w", function(offset, data, mask)
  if (mask & 0xff00) == 0 then return end
  if ((data >> 8) & 0xff) ~= 0 then                       -- the count moved (the vblank handler, or the forced write)
    if t0 and not in_wait and not t_move then t_move, unit_pc = now(), last_pc end
    return
  end
  local pc = pcst.value
  if pc < 0xfe1400 or pc > 0xfe140e then return end
  local t = now()
  if t0 and t_end then
    local f = {}
    local function us(x) return x and string.format("%.1f", (x - t0) * 1e6) or "-1" end
    for k = 1, #codes do f[#f + 1] = us(first[k]) end
    out:write(string.format("M %d %.1f %s %s %s %d %.1f %s %x %s %x %d%s\n", frame, (t_end - t0) * 1e6,
      us(ret), us(body), table.concat(f, " "), hcalls, hus, us(t_move), unit_pc, us(trip), trip_pc, forced,
      schi > sclo and (" " .. us(s_last)) or ""))
  end
  t0, body, first, in_wait, t_end, ret, hcalls, hus, h_in, h_last = t, nil, {}, false, nil, nil, 0, 0.0, nil, nil
  t_move, unit_pc, last_pc, trip, trip_pc, forced = nil, 0, 0, nil, 0, 0
  s_last = nil
end)
if schi > sclo then
  local a, b = sclo & ~1, (schi - 1) | 1
  local function sacc() if t0 and not in_wait then s_last = now() end end
  _G.vr_makeup_sr = prog:install_read_tap(a, b, "vr_makeup_sr", function() sacc() end)
  _G.vr_makeup_sw = prog:install_write_tap(a, b, "vr_makeup_sw", function() sacc() end)
end
if thi > tlo then
  _G.vr_makeup_ret = prog:install_read_tap(0x520000, 0x520001, "vr_makeup_ret", function(offset, data, mask)
    local pc = pcst.value
    if t0 and not body and pc >= tlo and pc < thi then ret = now() end     -- the stub's last read of SWITCH / STATE before the body
  end)
end
_G.vr_makeup_nshow = prog:install_write_tap(nshow, nshow + 3, "vr_makeup_nshow", function(offset, data, mask)
  if t0 and not body then
    body = now()
    shows = shows + 1
    if force_every and shows % force_every == 0 then forced = 1; prog:write_u8(0x500501, 1) end
  end
end)
if shi > slo then
  _G.vr_makeup_stub = prog:install_read_tap(0x502294, 0x502297, "vr_makeup_stub", function(offset, data, mask)
    local pc = pcst.value
    if t0 and pc >= slo and pc < shi then close_call(); h_in = now(); hcalls = hcalls + 1 end
  end)
  local function hcell() if h_in then h_last = now() end end
  _G.vr_makeup_hr = prog:install_read_tap(hlo, hhi, "vr_makeup_hr", function() hcell() end)
  _G.vr_makeup_hw = prog:install_write_tap(hlo, hhi, "vr_makeup_hw", function() hcell() end)
end
_G.vr_makeup_stop = emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
