-- Phase 26 stage 3 (Task 2): the COURSE DIRECTION screen's log. One line at every frame end at which a field differs from the
-- last line written (the timer steps once a logic frame on the select screen, so about every second frame there):
--   D <frame> <mode 0x501139> <state 0x501180> <timer 0x50113c> <handler> <entry 0x501940> <flag> <phase> <armed> <shown>
--     <edge 0x501078> <manual 0x501936> <start: bit 4 of 0x501050, the START button as 0xfc31e4 reads it> <counter 0x501144>
-- mode, handler and edge hex, the rest decimal; the timer signed; the counter (u32) is the game's logic frame counter (Task 3:
-- a logic frame the V60 overruns shows as a step that takes more than two video frames); the handler is the select entity's ([0x501318] + 0xa) while the
-- mode byte reads 0x10, else 0; flag, phase, armed and shown are the four bytes from VR_DIRECTION_RAM (hex, course.DIRECTION_RAM:
-- the flag, then dirscreen.DIR_PHASE, DIR_ARMED, DIR_SHOWN). Frames are counted from 1 at the first frame end, as autoplay.lua
-- counts them. Loaded by autoplay.lua when VR_DIR_LOG (path) is set; VR_DIRECTION_RAM missing or not hex is an error.
local out = assert(io.open(os.getenv("VR_DIR_LOG"), "w"))
local flag_at = tonumber(os.getenv("VR_DIRECTION_RAM") or "", 16)
if not flag_at then error("dirscreen_log.lua: VR_DIRECTION_RAM is missing or not hex: " .. tostring(os.getenv("VR_DIRECTION_RAM"))) end
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local frame, last = 0, ""
local function s32(a) local v = mem:read_u32(a); if v >= 0x80000000 then v = v - 0x100000000 end; return v end
emu.register_frame_done(function()
  frame = frame + 1
  local mode = mem:read_u8(0x501139)
  local handler = 0
  if mode == 0x10 then
    local e = mem:read_u32(0x501318)
    if e >= 0x400000 and e < 0x600000 then handler = mem:read_u32(e + 0xA) end
  end
  local s = string.format("%02x %d %d %x %d %d %d %d %d %x %d %d %d", mode, mem:read_u8(0x501180), s32(0x50113C), handler,
    mem:read_u8(0x501940), mem:read_u8(flag_at), mem:read_u8(flag_at + 1), mem:read_u8(flag_at + 2), mem:read_u8(flag_at + 3),
    mem:read_u16(0x501078), mem:read_u8(0x501936), (mem:read_u32(0x501050) >> 4) & 1, mem:read_u32(0x501144))
  if s ~= last then out:write(string.format("D %d %s\n", frame, s)); out:flush(); last = s end
end)
