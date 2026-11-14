-- Phase 26: the wrong-way warning's positive control. Every frame the next-mode byte 0x501139 reads 0x14 (the race; see
-- direction.lua for the two mode bytes) this writes 0 to the direction byte at VR_DIRECTION_RAM (hex; course.DIRECTION_RAM,
-- 0x502294). By then the loader (mode 0x11) has served the reverse variant and written back 1, so the car drives the reversed
-- tables while `dirattr` returns the quads' direction as authored: the game sees the car travelling against its quads. It writes
-- nothing else and nothing before the race. Loaded with VR_EXTRA_LUA. Env: VR_DIRECTION_RAM (an error when missing or not hex).
local addr = tonumber(os.getenv("VR_DIRECTION_RAM") or "", 16)
if not addr then error("direction_off.lua: VR_DIRECTION_RAM is missing or not hex: " .. tostring(os.getenv("VR_DIRECTION_RAM"))) end
local mem = manager.machine.devices[":maincpu"].spaces["program"]
emu.register_frame_done(function()
  if mem:read_u8(0x501139) == 0x14 then mem:write_u8(addr, 0) end
end)
