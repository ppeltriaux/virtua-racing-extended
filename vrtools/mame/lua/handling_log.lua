-- Weather stage 5: the player's handling, frame by frame, and scripted inputs (tests/test_weather_handling.py). Rewritten from the
-- handling prototype's scratch logger (spike 54's p54_log.lua). Loaded with VR_EXTRA_LUA after autoplay.lua: its frame callback runs
-- after autoplay's (and the autopilot's), so its inputs win for the frames they cover. Env:
--   VR_HANDLING_LOG    output path (required)
--   VR_HANDLING_CELLS  hex: the handling module's first cell (the carrier lays it out; 0 or unset: the cells are logged as 0)
--   VR_HANDLING_FROM   log from race start + this many frames (default -5)
--   VR_HANDLING_ACT    actions, ';'-separated "<trig><n>[@<race>],<port>,<value>,<delay>,<frames>[,<on>,<off>]": trig `at` (race
--                      start + n frames; the first race only), `rp` (the first frame 60 frames or more into the race at which the
--                      player's road point +0xa6 is n..n+39), `kmh` (the first frame 2 or more into the race at km/h >= n), `mode` (the
--                      first frame the mode byte 0x501138 reads n, hex digits), `glide` (the first frame [0x501160] > 0, n unused),
--                      `spin` (the first frame the player's spin-out +0x6c runs), `pit` (the first frame of the race mode at which the
--                      player's pit state +0x191 is nonzero: the grid start's crew sets it in the countdown), `fired` (the first frame the
--                      handling's spins counter is n or more: the wet spin, not the game's own grass spin-out); `race` (default 1) counts the races of the run (a race begins at the first frame its countdown,
--                      mode 0x12, is read after a mode outside 0x12-0x14); `delay` frames after the trigger the port holds `value` for
--                      `frames` frames, with `on`,`off` given `value` for `on` frames then 0 for `off`, repeated (taps). Ports: wheel,
--                      gas, brake (the inputs: after its frames the wheel goes back to 128, the brake to 0, the gas to autoplay's) and
--                      clock (the race clock 0x50116c written `value` on each of its frames: 0 ends the race by time over), slip and note
--                      (the handling's slip mark and engine note written `value`: a forced stale state, VR_HANDLING_CELLS needed).
-- Lines (frames count from 1 at the first frame end, as autoplay.lua's; an F line is written at each logic pass's end, the others at
-- frame ends):
--   T <frame> <rel> <trig><n> <port>                    an action's trigger
--   F <frame> <rel> <race> <mode hex> <handler hex> <flags hex> <gas> <brake> <gear> <km/h> <traction> <lock timer +0x64> <smoke +0x65>
--     <yaw +0x6a> <path +0x36> <L +0x154> <S +0x14e> <grip +0x164> <spin-out +0x6c (byte)> <crash +0x56> <x> <z> <covered> <pit +0x191>
--     <glide 0x501160> <road point +0xa6> <lap +0x1b5> <engine 0x503004 hex> <squeal 0x503008 hex> <switch 0x520000> <lock> <cool-down>
--     <slip> <lock count> <engine note> <spins> <locks> <locked frames> <slip frames> <steering skips> <opponents' +0x48, 15 hex words>
--     <rpm +0x15a> <opponents' +0x3c (their base), 15 hex words> <the player's own +0x48, hex>
--   L <frame> <rel> <car> <lap>                          a car's lap counter changed
--   C <frame> <calls of each stub of VR_HANDLING_STUBS since the last C line>  (only with VR_HANDLING_STUBS)
-- The last line is "END".
local path = assert(os.getenv("VR_HANDLING_LOG"), "handling_log.lua: VR_HANDLING_LOG is not set")
local out = assert(io.open(path, "w"))
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local cells = tonumber(os.getenv("VR_HANDLING_CELLS") or "0", 16) or 0
local from = tonumber(os.getenv("VR_HANDLING_FROM") or "-5")
local function fld(tag, name)
  for n, f in pairs(manager.machine.ioport.ports[tag].fields) do if n == name then return f end end
  error("handling_log.lua: no field " .. name .. " on " .. tag)
end
local ports = {wheel = fld(":WHEEL", "Paddle"), gas = fld(":ACCEL", "P1 Pedal 1"), brake = fld(":BRAKE", "P1 Pedal 2")}
local function put(port, v)
  if port == "clock" then mem:write_u32(0x50116c, v)
  elseif port == "slip" then if cells ~= 0 then mem:write_u8(cells + 2, v) end
  elseif port == "note" then if cells ~= 0 then mem:write_u32(cells + 4, v) end
  else ports[port]:set_value(v) end
end
local acts = {}
for item in string.gmatch(os.getenv("VR_HANDLING_ACT") or "", "[^;]+") do
  local kind, n, race, rest = string.match(item, "^(%l+)(%x*)@?(%d*),(.+)$")
  local f = {}
  for v in string.gmatch(rest or "", "[^,]+") do f[#f + 1] = v end
  assert(kind and #f >= 4 and (ports[f[1]] or f[1] == "clock" or f[1] == "slip" or f[1] == "note"), "handling_log.lua: bad action " .. item)
  acts[#acts + 1] = {kind = kind, n = tonumber(n, kind == "mode" and 16 or 10) or 0, race = tonumber(race) or 1, port = f[1],
                     v = tonumber(f[2]), d = tonumber(f[3]), k = tonumber(f[4]), on = tonumber(f[5] or ""), off = tonumber(f[6] or ""),
                     trig = nil}
end
local B = 0x400d00
local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
local function s16(a) local v = mem:read_u16(a); return v >= 0x8000 and v - 0x10000 or v end
local function s8(a) local v = mem:read_u8(a); return v >= 0x80 and v - 0x100 or v end
local function cell_b(k) return cells ~= 0 and mem:read_u8(cells + k) or 0 end
local function cell_w(k) return cells ~= 0 and mem:read_u32(cells + 4 * k) or 0 end
-- VR_HANDLING_STUBS "name=lo-hi,..." (hex): the stubs' address ranges; each stub's read of the weather byte counted (its calls)
local stubs, calls = {}, {}
for name, lo, hi in string.gmatch(os.getenv("VR_HANDLING_STUBS") or "", "(%w+)=(%x+)-(%x+)") do
  stubs[#stubs + 1] = {name, tonumber(lo, 16), tonumber(hi, 16)}
  calls[#calls + 1] = 0
end
if #stubs > 0 then
  local pcst = manager.machine.devices[":maincpu"].state["PC"]
  _G.vr_handling_calls = mem:install_read_tap(0x502296, 0x502297, "vr_handling_calls", function(offset, data, mask)
    local pc = pcst.value
    for k, st in ipairs(stubs) do if pc >= st[2] and pc < st[3] then calls[k] = calls[k] + 1 end end
  end)
end
local frame, laps, race, race_at, prev_mode = 0, {}, 0, 0, 0
local function write_pass()
  local rs = type(_G.vr_race_start) == "function" and _G.vr_race_start() or nil
  if not rs then return end
  local rel, rp, mode = frame - rs, s16(B + 0xa6), mem:read_u8(0x501138)
  if rel >= from then
    local opp, base = {}, {}
    for car = 1, 15 do
      opp[#opp + 1] = string.format("%x", mem:read_u32(B + 0x280 * car + 0x48))
      base[#base + 1] = string.format("%x", mem:read_u32(B + 0x280 * car + 0x3c))
    end
    out:write(string.format("F %d %d %d %x %x %x %d %d %d %d %.5f %d %d %d %d %d %d %d %d %d %.3f %.3f %d %d %d %d %d %x %x %d %d %d %d %d %d %d %d %d %d %d %s %d %s %x\n",
      frame, rel, race, mode, mem:read_u32(B + 0xa), mem:read_u32(B), mem:read_u16(B + 0x109), mem:read_u16(B + 0x105),
      mem:read_u32(B + 0x156), mem:read_u32(B + 0x14), f32(B + 0x5c), mem:read_u8(B + 0x64), mem:read_u8(B + 0x65), s16(B + 0x6a),
      s16(B + 0x36), s16(B + 0x154), s16(B + 0x14e), mem:read_i32(B + 0x164), mem:read_u8(B + 0x6c), mem:read_u8(B + 0x56), f32(B + 0x1e),
      f32(B + 0x26), mem:read_u8(B + 0x152) >> 7, s16(B + 0x191), mem:read_i32(0x501160), rp, s8(B + 0x1b5),
      mem:read_u16(0x503004), mem:read_u16(0x503008), mem:read_u8(0x520000), cell_b(0), cell_b(1), cell_b(2), cell_b(3), cell_w(1),
      cell_w(2), cell_w(3), cell_w(4), cell_w(5), cell_w(6), table.concat(opp, ","), mem:read_u32(B + 0x15a), table.concat(base, ","), mem:read_u32(B + 0x48)))
  end
end
-- the F line at each pass's end: the exit of the game's two-vblank wait (its write of 0 to the vblank count 0x500501 from
-- 0xfe1400..0xfe140e, as frame_rate.lua's), so a pass's fields are read whole whatever a video frame's end falls inside
local pcst_f = manager.machine.devices[":maincpu"].state["PC"]
_G.vr_handling_pass = mem:install_write_tap(0x500500, 0x500501, "vr_handling_pass", function(offset, data, mask)
  if (mask & 0xff00) == 0 or ((data >> 8) & 0xff) ~= 0 then return end
  local pc = pcst_f.value
  if pc >= 0xfe1400 and pc <= 0xfe140e then write_pass() end
end)
-- VR_HANDLING_COVER "from:to" (race-relative frames; `to` "k<n>": until the first race frame at km/h >= n): every write of the
-- player's segment flag +0x152 in that window has its bit 7 (the tunnel flag) set: the player "under cover" on any road (the game
-- itself reads that bit only for its tunnel sound)
local cover_kmh, cover_end = nil, nil
do
  local cf, ct = string.match(os.getenv("VR_HANDLING_COVER") or "", "(%-?%d+):(k?%d+)")
  if cf then
    cf = tonumber(cf)
    if ct:sub(1, 1) == "k" then cover_kmh, ct = tonumber(ct:sub(2)), 1 << 30 else ct = tonumber(ct) end
    local flag = B + 0x152
    _G.vr_handling_cover = mem:install_write_tap(flag & ~3, (flag & ~3) + 3, "vr_handling_cover", function(offset, data, mask)
      local rs = type(_G.vr_race_start) == "function" and _G.vr_race_start() or nil
      if not rs or frame - rs < cf or frame - rs >= ct or offset > flag or flag - offset > 3 then return end
      if cover_end and frame >= cover_end then return end
      local bit = 0x80 << (8 * (flag - offset))
      if mask & bit ~= 0 then return data | bit end
    end)
  end
end
-- VR_HANDLING_TRACE hex (a measurement build's trace cell, with VR_HANDLING_STUBS): each hook call timed from its stub's read of the
-- weather byte to the write of its exit's number into the cell; at the end, per site and exit number:
--   P <site index> <exit> <calls> <median us> <mean us> <min us> <max us>
do
  local cell = tonumber(os.getenv("VR_HANDLING_TRACE") or "", 16)
  if cell and #stubs > 0 then
    local pcst = manager.machine.devices[":maincpu"].state["PC"]
    local function now() return manager.machine.time:as_double() end
    local t0, site, times = nil, nil, {}
    _G.vr_handling_trace_in = mem:install_read_tap(0x502296, 0x502297, "vr_handling_trace_in", function(offset, data, mask)
      local pc = pcst.value
      for k, st in ipairs(stubs) do if pc >= st[2] and pc < st[3] then t0, site = now(), k end end
    end)
    _G.vr_handling_trace_out = mem:install_write_tap(cell & ~1, (cell & ~1) + 1, "vr_handling_trace_out", function(offset, data, mask)
      local shift = 8 * (cell - offset)
      if not t0 or (mask >> shift) & 0xff == 0 then return end
      local key = site .. " " .. ((data >> shift) & 0xff)
      times[key] = times[key] or {}
      local t = times[key]
      t[#t + 1] = (now() - t0) * 1e6
      t0 = nil
    end)
    _G.vr_handling_trace_stop = emu.add_machine_stop_notifier(function()
      for key, t in pairs(times) do
        table.sort(t)
        local sum = 0
        for _, v in ipairs(t) do sum = sum + v end
        out:write(string.format("P %s %d %.3f %.3f %.3f %.3f\n", key, #t, t[(#t + 1) // 2], sum / #t, t[1], t[#t]))
      end
    end)
  end
end
emu.register_frame_done(function()
  frame = frame + 1
  local rs = type(_G.vr_race_start) == "function" and _G.vr_race_start() or nil
  if not rs then return end
  local rel = frame - rs
  local rp = s16(B + 0xa6)
  local mode = mem:read_u8(0x501138)
  if cover_kmh and not cover_end and mode == 0x14 and mem:read_u32(B + 0x14) >= cover_kmh then cover_end = frame end
  if mode == 0x12 and (prev_mode < 0x12 or prev_mode > 0x14) then race, race_at = race + 1, frame end
  prev_mode = mode
  local into = race > 0 and frame - race_at or -1
  for _, a in ipairs(acts) do
    if not a.trig and a.race == math.max(race, 1) then             -- before the first countdown: the first race's load
      if (a.kind == "at" and race <= 1 and rel >= a.n) or (a.kind == "rp" and into > 60 and rp >= a.n and rp < a.n + 40)
         or (a.kind == "kmh" and into > 2 and mem:read_u32(B + 0x14) >= a.n) or (a.kind == "mode" and mode == a.n)
         or (a.kind == "glide" and mem:read_i32(0x501160) > 0) or (a.kind == "spin" and mem:read_u8(B + 0x6c) ~= 0)
         or (a.kind == "pit" and mode == 0x14 and mem:read_u16(B + 0x191) ~= 0) or (a.kind == "fired" and cell_w(2) >= a.n) then
        a.trig = frame
        out:write(string.format(a.kind == "mode" and "T %d %d %s%x %s\n" or "T %d %d %s%d %s\n", frame, rel, a.kind, a.n, a.port))
      end
    end
    if a.trig then
      local t = frame - a.trig
      if t >= a.d and t < a.d + a.k then
        local v = a.v
        if a.on and a.off and (t - a.d) % (a.on + a.off) >= a.on then v = 0 end
        put(a.port, v)
      elseif t == a.d + a.k then
        if a.port == "wheel" then ports.wheel:set_value(128) elseif a.port == "brake" then ports.brake:set_value(0) end
      end
    end
  end
  for car = 0, 15 do
    local lap = s8(B + 0x280 * car + 0x1b5)
    if laps[car] ~= lap then
      if laps[car] ~= nil then out:write(string.format("L %d %d %d %d\n", frame, rel, car, lap)) end
      laps[car] = lap
    end
  end
  if #stubs > 0 then
    out:write(string.format("C %d %s\n", frame, table.concat(calls, " ")))
    for k = 1, #calls do calls[k] = 0 end
  end
  if frame % 100 == 0 then out:flush() end
end)
_G.vr_handling_stop = emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
