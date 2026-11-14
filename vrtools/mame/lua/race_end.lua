-- Phase 26 stage 3 (Task 1): a one-lap race with the clock held, and what follows it: the record, the attract, a second game.
-- Loaded with VR_EXTRA_LUA alongside autoplay.lua (its frame callback runs after autoplay's and direction.lua's). Env:
--   VR_END_LOG    the log (required)
--   VR_END_TABLE  "lo-hi" (hex): a write tap on that RAM range (a ranking table) from the race load on
--   VR_END_COIN   n: a coin, then START, once the n-th attract pit scene (mode 0x07) after the race has ended (none when unset)
--   VR_DIRECTION_RAM  the flag's address (hex, course.DIRECTION_RAM; required)
-- The race load is the first frame end the next-mode byte 0x501139 reads 0x11. From then until the race ends (the first mode
-- outside 0x11..0x14 after it) this writes 1 to the lap count 0x5011a4 in modes 0x12-0x14, and in mode 0x14 the race clock
-- 0x50116c back to 1920 whenever it is below 600, so the car finishes the lap before the clock runs out. Lines:
--   L <frame>                                                      the race load
--   M <frame> <mode 0x501139> <state 0x501180> <flag> <record 0x5018fc> <handler>
--       every frame end at which one of them changes (hex but the frame and the state); the handler is the select entity's
--       ([0x501318] + 0xa) while the mode byte reads 0x10, else 0
--   W <frame> <pc> <address> <data>                                 a write into VR_END_TABLE (hex but the frame)
--   C <frame>                                                       the coin
-- Frames are counted from 1 at the first frame end, as autoplay.lua counts them.
local out = assert(io.open(assert(os.getenv("VR_END_LOG"), "race_end.lua: VR_END_LOG is not set"), "w"))
local cpu = manager.machine.devices[":maincpu"]
local mem = cpu.spaces["program"]
local function field(tag, name)
  local port = manager.machine.ioport.ports[tag]
  if not port then error("race_end.lua: no port " .. tag) end
  for n, f in pairs(port.fields) do if n == name then return f end end
  error("race_end.lua: no field " .. name .. " on " .. tag)
end
local coin, start = field(":IN.0", "Coin 1"), field(":IN.0", "1 Player Start")
local lo, hi = string.match(os.getenv("VR_END_TABLE") or "", "(%x+)-(%x+)")
local coin_after = tonumber(os.getenv("VR_END_COIN") or "")
local flag_at = tonumber(os.getenv("VR_DIRECTION_RAM") or "", 16)
if not flag_at then error("race_end.lua: VR_DIRECTION_RAM is missing or not hex: " .. tostring(os.getenv("VR_DIRECTION_RAM"))) end
local frame, load, racing, last, scenes, in_scene, coin_at = 0, nil, false, "", 0, false, nil
_G.vr_race_end_taps = {}

emu.register_frame_done(function()
  frame = frame + 1
  local mode = mem:read_u8(0x501139)
  if not load and mode == 0x11 then
    load, racing = frame, true
    out:write(string.format("L %d\n", frame))
    if lo then
      _G.vr_race_end_taps[1] = mem:install_write_tap(tonumber(lo, 16), tonumber(hi, 16), "race_end_table", function(offset, data, mask)
        out:write(string.format("W %d %x %x %x\n", frame, cpu.state["PC"].value, offset, data))
      end)
    end
  end
  if racing then
    if mode < 0x11 or mode > 0x14 then racing = false
    elseif mode >= 0x12 then
      mem:write_u8(0x5011A4, 1)
      if mode == 0x14 and mem:read_i32(0x50116C) < 600 then mem:write_u32(0x50116C, 1920) end
    end
  end
  local handler = 0
  if mode == 0x10 then
    local e = mem:read_u32(0x501318)
    if e >= 0x400000 and e < 0x600000 then handler = mem:read_u32(e + 0xA) end
  end
  local s = string.format("%02x %d %02x %x %x", mode, mem:read_u8(0x501180), mem:read_u8(flag_at), mem:read_u32(0x5018FC), handler)
  if s ~= last then out:write(string.format("M %d %s\n", frame, s)); last = s end
  if load and not racing and coin_after and not coin_at then                -- the attract's pit scenes after the race
    if mode == 0x07 then in_scene = true
    elseif in_scene then
      in_scene, scenes = false, scenes + 1
      if scenes == coin_after then coin_at = frame + 1 end
    end
  end
  if coin_at then
    local t = frame - coin_at
    if t == 0 then coin:set_value(1); out:write(string.format("C %d\n", frame)) elseif t == 10 then coin:set_value(0)
    elseif t == 40 then start:set_value(1) elseif t == 50 then start:set_value(0) end
  end
  out:flush()
end)
