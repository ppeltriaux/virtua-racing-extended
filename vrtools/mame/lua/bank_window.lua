-- Weather, the final review's W8 (tests/test_weather_carrier.py's test_no_interrupt_reads_the_storms_bank): what reads the data
-- bank window 0x100000..0x1fffff while the storm's load has another bank mapped. Lines:
--   B <frame> <us> <pc> <value>        every write of the bank register 0xe00004 (pc hex, the value written hex)
--   W <frame> <us> <pc> <addr> <bank>  a window read from outside the storm stub (VR_BW_STUB "lo,hi" hex) while the last bank
--                                      register write came from the stub and is not the course's own bank (VR_BW_BANK hex: the
--                                      value the stub restores): the storm's bank is mapped
--   I <frame> <us> <pc>                the vblank interrupt's vector fetch (0xfff104), frames VR_BW_FROM..VR_BW_FROM+600
--   P <frame> <vblank ticks> <passes>  at each frame end from VR_BW_FROM for 600 frames: the game's vblank tick counter 0x40e8f0
--                                      (the handler counts it every vblank outside the TEST menu) and the passes counted here (the
--                                      game's write of 0 to 0x500501 at its wait's exit, 0xfe1400..0xfe140e)
-- us: emulated microseconds. Env: VR_BW_LOG (path), VR_BW_STUB, VR_BW_BANK, VR_BW_FROM (frame). Loaded by autoplay.lua through VR_EXTRA_LUA.
local path = os.getenv("VR_BW_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local cpu = manager.machine.devices[":maincpu"]
  local prog = cpu.spaces["program"]
  local pcst = cpu.state["PC"]
  local lo, hi = string.match(os.getenv("VR_BW_STUB") or "", "(%x+),(%x+)")
  if not lo then error("bank_window.lua: VR_BW_STUB lo,hi") end
  lo, hi = tonumber(lo, 16), tonumber(hi, 16)
  local from = tonumber(os.getenv("VR_BW_FROM") or "0")
  local own = tonumber(os.getenv("VR_BW_BANK") or "", 16)
  if not own then error("bank_window.lua: VR_BW_BANK (the course's bank register value, hex)") end
  local frame, passes, by_stub, bank = 0, 0, false, -1
  local function us() return manager.machine.time:as_double() * 1e6 end
  emu.register_frame_done(function()
    frame = frame + 1
    if frame >= from and frame < from + 600 then
      out:write(string.format("P %d %d %d\n", frame, prog:read_u32(0x40E8F0), passes))
    end
  end)
  _G.vr_bw_pass = prog:install_write_tap(0x500500, 0x500501, "vr_bw_pass", function(offset, data, mask)
    local pc = pcst.value
    if pc >= 0xfe1400 and pc <= 0xfe140e then passes = passes + 1 end
  end)
  _G.vr_bw_bank = prog:install_write_tap(0xE00004, 0xE00007, "vr_bw_bank", function(offset, data, mask)
    local pc = pcst.value
    by_stub, bank = pc >= lo and pc < hi, data & 0xff
    out:write(string.format("B %d %.3f %x %x\n", frame, us(), pc, bank))
  end)
  _G.vr_bw_win = prog:install_read_tap(0x100000, 0x1FFFFF, "vr_bw_win", function(offset, data, mask)
    if not by_stub or bank == own then return end
    local pc = pcst.value
    if pc >= lo and pc < hi then return end
    out:write(string.format("W %d %.3f %x %x %x\n", frame, us(), pc, offset, bank))
  end)
  _G.vr_bw_vec = prog:install_read_tap(0xfff104, 0xfff105, "vr_bw_vec", function(offset, data, mask)
    if frame >= from and frame < from + 600 and (mask & 0xffff) ~= 0 then
      out:write(string.format("I %d %.3f %x\n", frame, us(), pcst.value))
    end
  end)
  emu.add_machine_stop_notifier(function() out:write("END\n"); out:close() end)
end
