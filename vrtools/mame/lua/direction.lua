-- Phase 26: the direction switch. Every frame the next-mode byte 0x501139 reads 0x10 (the select screen) this writes VR_DIRECTION
-- (0 normal, 1 reverse) to the byte at VR_DIRECTION_RAM (hex; course.DIRECTION_RAM, 0x502294). The course loader (mode 0x11)
-- reads that byte when the race loads and writes back what it served, so nothing here writes at any other time.
-- The mode bytes (dispatcher 0xfe1c7d, every 2 video frames): the dispatcher copies 0x501139 to 0x501138 and runs the handler of
-- 0x501138; a handler changes mode by writing 0x501139. This reads 0x501139 because it is the mode the next dispatch runs: the
-- writes stop at the first frame end after mode 0x10's state 6 requests 0x11 (0xfe3fa8), before the loader's handler runs.
-- Stage 3: mode 0x10's state 0 clears the byte (dirscreen.py), but this writes it again at the end of that frame and every frame
-- after, so the switch holds.
-- Stage 3 Task 2 (plan D14): the COURSE DIRECTION screen sets the flag on a course with a variant, and autoplay.lua answers it
-- (VR_DIRECTION=1: REVERSE); this script stays a test tool for holding the flag where no screen sets it (the originals, a
-- course without a variant, the operator's fixed course). Standalone (VR_EXTRA_LUA) or loaded by autoplay.lua when
-- VR_DIRECTION_FORCE=1. Env: VR_DIRECTION, VR_DIRECTION_RAM.
-- VR_DIRECTION set with VR_DIRECTION_RAM missing or not hex is an error (it used to disable the switch silently).
local want = tonumber(os.getenv("VR_DIRECTION"))
if os.getenv("VR_DIRECTION") then
  local addr = tonumber(os.getenv("VR_DIRECTION_RAM") or "", 16)
  if not addr then
    error("direction.lua: VR_DIRECTION is set but VR_DIRECTION_RAM is missing or not hex: " .. tostring(os.getenv("VR_DIRECTION_RAM")))
  end
  if not want then error("direction.lua: VR_DIRECTION is not a number: " .. os.getenv("VR_DIRECTION")) end
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  emu.register_frame_done(function()
    if mem:read_u8(0x501139) == 0x10 then mem:write_u8(addr, want) end
  end)
end
