-- Weather stage 6: sound words put into the V60's own sound queue (0x503020, 32 entries, count 0x503001, tail 0x503003: the game's
-- entry 0xffa246 does the same) at chosen frame ends, the game sending them as its own; for measuring the storm's sounds alone in the
-- attract (no coin: nothing else of the storm). The autoboot script itself. Env:
--   VR_SOUND_INJECT  "frame:hhhh,..." (frames decimal, counted from 1 at the first frame end; words hex)
--   VR_PCM_LOG       pcm_log.lua's log (loaded from VR_LUA_DIR)
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local sched = {}
for f, w in string.gmatch(os.getenv("VR_SOUND_INJECT") or "", "(%d+):(%x+)") do sched[#sched + 1] = {tonumber(f), tonumber(w, 16)} end
local frame, idx = 0, 1
emu.register_frame_done(function()
  frame = frame + 1
  while idx <= #sched and sched[idx][1] <= frame do
    local n, tail = mem:read_u8(0x503001), mem:read_u8(0x503003)
    if n < 0x20 then
      mem:write_u16(0x503020 + 2 * tail, sched[idx][2])
      mem:write_u8(0x503003, (tail + 1) & 0x1f)
      mem:write_u8(0x503001, n + 1)
    end
    idx = idx + 1
  end
end)
local lua_dir = os.getenv("VR_LUA_DIR")
if os.getenv("VR_PCM_LOG") and lua_dir then dofile(lua_dir .. "/pcm_log.lua") end
