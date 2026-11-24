-- Weather stage 2: the storm's carrier and rain, pass by pass (weather/carrier.py's RAM contract). One line per pass of the main
-- loop, written at the exit of the wait that ends it (the write of 0 to 0x500501 from 0xfe1400..0xfe140e, as frame_rate.lua and
-- stale_list.lua: the frame is the same as their lines'):
--   S <frame> <state> <switch> <loads> <start passes> <show passes> <SBR hex> <clusters drawn> <splashes drawn> <late passes>
--     <budget trims: clusters> <splashes> <late trims (the guard): clusters> <splashes> <clusters placed> <active> <grade rows left>
--     <records before the rain> <after>
-- (the rain's counters from its state cells at VR_STORM_RAIN, hex: the carrier lays them out; the per-pass ones are the pass's,
-- the others cumulative). With VR_STORM_TRACE=1 also, for every pass with a write into the storm's RAM (0x520000..0x53efff) or to
-- the interval timer's period (0xe00008):
--   T <frame> <writes into the storm RAM> <first writer's pc hex> <its address hex> <timer writes>
-- A dump of the colour-translation RAM (96 rows of 64 halfwords: 0x910000 + channel 0x4000 + value 0x200) and of the backdrop's
-- palette RAM (0x900c00, 512 colours), at each frame of VR_STORM_DUMPS ("f1,f2,..."), two frames after each release (the state
-- from nonzero to 0) and, with VR_STORM_DUMP_AFTER_LOAD=n, n frames after each load (the state from 0 to nonzero):
--   X <frame> <hex>        P <frame> <hex>
-- and with VR_STORM_FULL=1 the whole palette RAM (0x900000..0x903fff) and the tile layers' maps (0x700000..0x707fff):
--   Q <frame> <hex>        M <frame> <hex>
-- For a pass in which the vblank count 0x500501 moved before the pass's work ended (the count written non-zero by the vblank
-- handler before the wait's first read, 0xfe13db..0xfe13f3), written with its S line:
--   A <frame> <microseconds from the count's move to the pass's end>
-- and, when a guard test of the storm's code (a read of the count from the storm's image, 0x522000..0x529fff) read it moved after the
-- move (the trip; the join, the session lead's split bound), also
--   B <frame> <microseconds from the move to the trip: the unit in flight> <from the trip to the pass's end: the tail>
-- With VR_STORM_WATCH=<hex address>[,<hex address>...] also, with each S line, the word at each (a later module's cell:
-- tests/test_weather_carrier.py's dummy module counts its calls in one; the join: the sound's counters):
--   W <frame> <hex> [<hex>...]
-- With VR_STORM_FRAMES=1 also, at every frame end where one of them changed (a frame callback: it survives MAME's soft reset,
-- which removes the memory taps the lines above hang on):
--   F <frame> <mode 0x501138 hex> <state> <switch> <SBR hex>
-- With VR_STORM_COVER=<hex: the cover's state cells>, VR_STORM_UC=<hex: its under_cover byte> and VR_STORM_COVER_FIELDS (the
-- logged words' indices in weather/cover.py's STATE: cover.log_env) also, with each S line:
--   C <frame> <mode> <under_cover> <hidden> <curtain clusters drawn> <single drops drawn> <placements> <roof (SILF)> <walk>
--     <nosplash> <cover's late passes> <the rain's splashes spawned (cumulative)> <camera x> <y> <z> <the box holding it, hex>
--     <the rain's clusters drawn this pass> <the player's car's y (+0x22)>
-- And with each S line (the final review's W9), the display list's high-water mark in the pass: the largest value the list pointer
-- 0x5017f4 was written with, as bytes from the start of its buffer (the game's two lists at 0x600000 and 0x610000, 64 KB each):
--   L <frame> <bytes>
-- And at each storm load's entry (the stub's first write, the load counter 0x520008 counted up by the stub; Task 7, the re-review: the load
-- masks interrupts and then ENABLES them unconditionally, correct only because the interrupt bit is set at the scenery call):
--   I <frame> <the PSW hex>
-- frame counts MAME frames from 1 at the first frame end. Env: VR_STORM_LOG (path), VR_STORM_RAIN (hex). The last line is "END".
local path = os.getenv("VR_STORM_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local cpu = manager.machine.devices[":maincpu"]
  local prog = cpu.spaces["program"]
  local pcst, sbr = cpu.state["PC"], cpu.state["SBR"]
  local rain = tonumber(os.getenv("VR_STORM_RAIN") or "", 16)
  if not rain then error("storm_log.lua: VR_STORM_RAIN is missing or not hex") end
  local trace = os.getenv("VR_STORM_TRACE") == "1"
  local full = os.getenv("VR_STORM_FULL") == "1"
  local dumps = {}
  for f in string.gmatch(os.getenv("VR_STORM_DUMPS") or "", "%d+") do dumps[tonumber(f)] = true end
  local after_load = tonumber(os.getenv("VR_STORM_DUMP_AFTER_LOAD") or "")
  local watch = {}
  for a in string.gmatch(os.getenv("VR_STORM_WATCH") or "", "%x+") do watch[#watch + 1] = tonumber(a, 16) end
  local cover = tonumber(os.getenv("VR_STORM_COVER") or "", 16)
  local uc = tonumber(os.getenv("VR_STORM_UC") or "", 16)
  local function cw(k) return prog:read_u32(cover + 4 * k) end
  -- the cover's state words logged, by their index in cover.STATE (VR_STORM_COVER_FIELDS, weather/cover.py's log_env: MODE HIDDEN
  -- CURDRAWN PDCOUNT PLACED SILF WALK NOSPLASH LATE CX CY CZ INBOX; fix round 1, M4: no index written here)
  local fi = {}
  for v in string.gmatch(os.getenv("VR_STORM_COVER_FIELDS") or "", "%d+") do fi[#fi + 1] = tonumber(v) end
  assert(not cover or #fi == 13, "storm_log.lua: VR_STORM_COVER needs VR_STORM_COVER_FIELDS (13 indices)")
  local function cf(k) return (string.unpack("<f", string.pack("<I4", cw(k)))) end
  local frame, lines, prev_state = 0, 0, 0
  local function now() return manager.machine.time:as_double() end
  local t_move, t_end, in_wait, t_trip = nil, nil, false, nil
  local writes, first_pc, first_addr, timer = 0, 0, 0, 0
  local function w(k) return prog:read_u32(rain + 4 * k) end
  local function dump()
    local x = {}
    for row = 0, 95 do
      local ch, c = row // 32, row % 32
      local base = 0x910000 + ch * 0x4000 + c * 0x200
      for l = 0, 63 do x[#x + 1] = string.format("%04x", prog:read_u16(base + 2 * l)) end
    end
    out:write(string.format("X %d %s\n", frame, table.concat(x)))
    local p = {}
    for k = 0, 511 do p[#p + 1] = string.format("%04x", prog:read_u16(0x900c00 + 2 * k)) end
    out:write(string.format("P %d %s\n", frame, table.concat(p)))
    if full then
      local q = {}
      for a = 0x900000, 0x903ffe, 2 do q[#q + 1] = string.format("%04x", prog:read_u16(a)) end
      out:write(string.format("Q %d %s\n", frame, table.concat(q)))
      local mm = {}
      for a = 0x700000, 0x707ffe, 2 do mm[#mm + 1] = string.format("%04x", prog:read_u16(a)) end
      out:write(string.format("M %d %s\n", frame, table.concat(mm)))
    end
  end
  local per_frame, last_f = os.getenv("VR_STORM_FRAMES") == "1", ""
  emu.register_frame_done(function()
    frame = frame + 1
    if dumps[frame] then dump(); out:flush() end
    if per_frame then
      local f = string.format("%02x %d %d %x", prog:read_u8(0x501138), prog:read_u8(0x520001), prog:read_u8(0x520000), sbr.value)
      if f ~= last_f then out:write(string.format("F %d %s\n", frame, f)); last_f = f; out:flush() end
    end
  end)
  -- the rain's state cells (rain.py: Rain.c's order)
  local ACTIVE, XLEFT, DRAWN, SPDRAWN, PRIMED, LATE, TRIM_CL, TRIM_SP, TRIM_LCL, TRIM_LSP, REC_IN, REC_OUT =
    0, 2, 7, 8, 16, 19, 20, 21, 22, 23, 25, 26
  local list_ptr, list_hw = prog:read_u32(0x5017F4), 0           -- W9: the list pointer's shadow and this pass's high-water mark
  _G.vr_storm_list = prog:install_write_tap(0x5017F4, 0x5017F7, "vr_storm_list", function(offset, data, mask)
    local shift = (offset - 0x5017F4) * 8
    list_ptr = ((list_ptr & ~(mask << shift)) | ((data & mask) << shift)) & 0xFFFFFFFF
    local used = list_ptr & 0xFFFF
    if (list_ptr & 0xFFFE0000) == 0x600000 and used > list_hw then list_hw = used end
  end)
  _G.vr_storm_wait = prog:install_read_tap(0x500500, 0x500501, "vr_storm_wait", function(offset, data, mask)
    if in_wait or (mask & 0xff00) == 0 then return end
    local pc = pcst.value
    if t_move and not t_trip and pc >= 0x522000 and pc < 0x52a000 and ((data >> 8) & 0xff) ~= 0 then t_trip = now() end   -- the trip
    if pc >= 0xfe13db and pc <= 0xfe13f3 then in_wait = true; t_end = now() end
  end)
  _G.vr_storm_exit = prog:install_write_tap(0x500500, 0x500501, "vr_storm_exit", function(offset, data, mask)
    if (mask & 0xff00) == 0 then return end
    local pc = pcst.value
    if ((data >> 8) & 0xff) ~= 0 then
      if not in_wait and not t_move then t_move = now() end            -- the vblank handler moved the count during the pass's work
      return
    end
    if pc < 0xfe1400 or pc > 0xfe140e then return end
    if t_move and t_end and t_end > t_move then
      out:write(string.format("A %d %.1f\n", frame, (t_end - t_move) * 1e6))
      if t_trip then out:write(string.format("B %d %.1f %.1f\n", frame, (t_trip - t_move) * 1e6, (t_end - t_trip) * 1e6)) end
    end
    t_move, t_end, in_wait, t_trip = nil, nil, false, nil
    local state = prog:read_u8(0x520001)
    out:write(string.format("S %d %d %d %d %d %d %x %d %d %d %d %d %d %d %d %d %d %d %d\n", frame, state, prog:read_u8(0x520000),
      prog:read_u32(0x520008), prog:read_u32(0x52000c), prog:read_u32(0x520010), sbr.value, w(DRAWN), w(SPDRAWN), w(LATE),
      w(TRIM_CL), w(TRIM_SP), w(TRIM_LCL), w(TRIM_LSP), w(PRIMED), w(ACTIVE), w(XLEFT), w(REC_IN), w(REC_OUT)))
    out:write(string.format("L %d %d\n", frame, list_hw))
    list_hw = 0
    if #watch > 0 then
      local w = {}
      for _, a in ipairs(watch) do w[#w + 1] = string.format("%x", prog:read_u32(a)) end
      out:write(string.format("W %d %s\n", frame, table.concat(w, " ")))
    end
    if cover and uc then
      out:write(string.format("C %d %d %d %d %d %d %d %d %d %d %d %d %.3f %.3f %.3f %x %d %.3f\n", frame, cw(fi[1]), prog:read_u8(uc), cw(fi[2]),
        cw(fi[3]), cw(fi[4]), cw(fi[5]), cw(fi[6]), cw(fi[7]), cw(fi[8]), cw(fi[9]), w(18), cf(fi[10]), cf(fi[11]), cf(fi[12]), cw(fi[13]),
        w(DRAWN), (string.unpack("<f", string.pack("<I4", prog:read_u32(0x400d22))))))
    end
    if trace and (writes > 0 or timer > 0) then
      out:write(string.format("T %d %d %x %x %d\n", frame, writes, first_pc, first_addr, timer))
    end
    writes, timer = 0, 0
    if prev_state ~= 0 and state == 0 then dumps[frame + 2] = true end
    if after_load and prev_state == 0 and state ~= 0 then dumps[frame + after_load] = true end
    prev_state = state
    lines = lines + 1
    if lines % 50 == 0 then out:flush() end
  end)
  local psw, last_i = cpu.state["PSW"], nil
  _G.vr_storm_load_psw = prog:install_write_tap(0x520008, 0x52000b, "vr_storm_load_psw", function(offset, data, mask)
    local pc = pcst.value                       -- the stub's add (its block 0xfff120..0xfff6df; the boot's RAM clear is not a load)
    if pc >= 0xfff120 and pc < 0xfff6e0 and last_i ~= frame .. ":" .. pc then   -- once an instruction (a 32-bit add: two writes)
      last_i = frame .. ":" .. pc
      out:write(string.format("I %d %x\n", frame, psw.value))
    end
  end)
  if trace then
    _G.vr_storm_trace = prog:install_write_tap(0x520000, 0x53efff, "vr_storm_trace", function(offset, data, mask)
      if writes == 0 then first_pc, first_addr = pcst.value, offset end
      writes = writes + 1
    end)
    _G.vr_storm_timer = prog:install_write_tap(0xe00008, 0xe0000b, "vr_storm_timer", function(offset, data, mask)
      timer = timer + 1
    end)
  end
  _G.vr_storm_stop = emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
end
