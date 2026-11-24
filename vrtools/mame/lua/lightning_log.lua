-- Weather stage 4: the lightning, pass by pass (weather/lightning.py). One line per pass of the main loop, written at the exit of
-- the wait that ends it (the write of 0 to 0x500501 from 0xfe1400..0xfe140e, as storm_log.lua: the frame is the same as its lines'):
--   L <frame> <the lightning's state words, hex, VR_LIGHT_WORDS of them from VR_LIGHT_STATE (weather/lightning.py STATE_NAMES)>
--     <strike_seq> <strike_band> <under_cover> <backdrop colours 1, 2, 3 (palette RAM 0x900c02..)> <colour RAM probes: channel 0
--     value 31 entry 32 (the white-out's first row), channel 2 value 0 entry 32 (its last row)>   (all hex)
-- and, for the passes in which the storm's code tested its time guard (a read of the vblank count 0x500501 from the storm's image,
-- VR_LIGHT_IMAGE "lo,hi" hex), the units between two tests:
-- (a time between two tests in which the game's vblank handler moved the count, 17.38 ms into the pass, is left out of these: it
-- holds the handler's own work, and storm_log.lua's A line bounds the time from that move to the pass's end):
--   G <frame> <tests> <the longest time between two tests, us> <the pc of the test it began at, hex> <the longest of those that
--     began in the lightning's code (VR_LIGHT_CODE "lo,hi" hex), us> <microseconds from the lightning's first test to the pass's
--     first test of the rain's code (VR_LIGHT_RAIN "lo,hi" hex), 0 when not both> <microseconds from the carrier's body (its show
--     counter's write, VR_LIGHT_NSHOW hex) to the pass's first test, 0 when none>
-- and at the run's end, per guard test of the storm's code (its pc), the longest time from it to the next test in the same pass and
-- how many such units there were (the units' table of the stage 4 findings):
--   U <pc hex> <longest, us> <units>
-- frame counts MAME frames from 1 at the first frame end. Env: VR_LIGHT_LOG (path). The last line is "END". Loaded by autoplay.lua.
local path = os.getenv("VR_LIGHT_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local cpu = manager.machine.devices[":maincpu"]
  local prog = cpu.spaces["program"]
  local pcst = cpu.state["PC"]
  local function hexpair(name)
    local a, b = string.match(os.getenv(name) or "", "(%x+),(%x+)")
    if not a then error("lightning_log.lua: " .. name .. " is missing (lo,hi hex)") end
    return tonumber(a, 16), tonumber(b, 16)
  end
  local state = tonumber(os.getenv("VR_LIGHT_STATE") or "", 16)
  local nwords = tonumber(os.getenv("VR_LIGHT_WORDS") or "")
  local seq = tonumber(os.getenv("VR_LIGHT_SEQ") or "", 16)
  local band = tonumber(os.getenv("VR_LIGHT_BAND") or "", 16)
  local cover = tonumber(os.getenv("VR_LIGHT_COVER") or "", 16)
  if not (state and nwords and seq and band and cover) then error("lightning_log.lua: VR_LIGHT_STATE/WORDS/SEQ/BAND/COVER") end
  local ilo, ihi = hexpair("VR_LIGHT_IMAGE")
  local clo, chi = hexpair("VR_LIGHT_CODE")
  local rlo, rhi = hexpair("VR_LIGHT_RAIN")
  local frame, lines = 0, 0
  local function now() return manager.machine.time:as_double() end
  local tests, last_t, last_pc, gap, gap_pc, lgap, first_l, first_r = 0, nil, 0, 0, 0, 0, nil, nil
  local unit_max, unit_n = {}, {}
  local moved = nil
  local body_t = nil
  local nshow = tonumber(os.getenv("VR_LIGHT_NSHOW") or "", 16)
  if nshow then
    _G.vr_light_body = prog:install_write_tap(nshow, nshow + 3, "vr_light_body", function(offset, data, mask)
      if not body_t then body_t = now() end
    end)
  end
  local first_t = nil
  emu.register_frame_done(function() frame = frame + 1 end)
  _G.vr_light_guard = prog:install_read_tap(0x500500, 0x500501, "vr_light_guard", function(offset, data, mask)
    if (mask & 0xff00) == 0 then return end
    local pc = pcst.value
    if pc < ilo or pc >= ihi then return end
    local t = now()
    if last_t and not (moved and moved > last_t and moved <= t) then
      local g = (t - last_t) * 1e6
      if g > gap then gap, gap_pc = g, last_pc end
      if last_pc >= clo and last_pc < chi and g > lgap then lgap = g end
      if g > (unit_max[last_pc] or 0) then unit_max[last_pc] = g end
      unit_n[last_pc] = (unit_n[last_pc] or 0) + 1
    end
    if pc >= clo and pc < chi and not first_l then first_l = t end
    if pc >= rlo and pc < rhi and not first_r then first_r = t end
    if not first_t then first_t = t end
    tests, last_t, last_pc = tests + 1, t, pc
  end)
  _G.vr_light_exit = prog:install_write_tap(0x500500, 0x500501, "vr_light_exit", function(offset, data, mask)
    if (mask & 0xff00) == 0 then return end
    if ((data >> 8) & 0xff) ~= 0 then
      if not moved then moved = now() end                                -- the vblank handler moved the count
      return
    end
    local pc = pcst.value
    if pc < 0xfe1400 or pc > 0xfe140e then return end
    local w = {}
    for k = 0, nwords - 1 do w[#w + 1] = string.format("%x", prog:read_u32(state + 4 * k)) end
    out:write(string.format("L %d %s %x %x %x %x %x %x %x %x\n", frame, table.concat(w, " "), prog:read_u32(seq), prog:read_u32(band),
      prog:read_u8(cover), prog:read_u16(0x900c02), prog:read_u16(0x900c04), prog:read_u16(0x900c06),
      prog:read_u16(0x910000 + 31 * 0x200 + 64), prog:read_u16(0x910000 + 2 * 0x4000 + 64)))
    if tests > 0 then
      local lr = (first_l and first_r and first_r > first_l) and (first_r - first_l) * 1e6 or 0
      local pre = (body_t and first_t and first_t > body_t) and (first_t - body_t) * 1e6 or 0
      out:write(string.format("G %d %d %.1f %x %.1f %.1f %.1f\n", frame, tests, gap, gap_pc, lgap, lr, pre))
    end
    tests, last_t, last_pc, gap, gap_pc, lgap, first_l, first_r = 0, nil, 0, 0, 0, 0, nil, nil
    moved, body_t, first_t = nil, nil, nil
    lines = lines + 1
    if lines % 50 == 0 then out:flush() end
  end)
  _G.vr_light_stop = emu.add_machine_stop_notifier(function()
    for pc, g in pairs(unit_max) do out:write(string.format("U %x %.1f %d\n", pc, g, unit_n[pc])) end
    out:write("END\n"); out:close()
  end)
end
