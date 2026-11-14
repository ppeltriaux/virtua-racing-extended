-- Phase 26 stage 4 (Task 4): the pit stop's record, loaded by autoplay.lua when VR_PIT_LOG names a file. From VR_PIT_FROM (default
-- 1600, the course load in this harness: the green follows at about 1864) one line per video frame for the player (entity
-- 0x400d00; the game logic steps every second frame, so every logic frame is logged), with the pit crew inline:
--   P <frame> <quad +0x150> <handler +0xa> <pit state +0x191> <stops +0x1bf> <x> <z> <yaw +0x6a> <speed +0x14> <clock 0x50116c>
--     <checkpoints +0x57> <lap +0x1b5> <flags +0> <smoke +0x1aa> <n> then n triples <x> <z> <heading +0x2c>
-- frame decimal, counted from 1 at the first frame end (as race_log.lua); the handler and the flags hex; the yaw and the heading
-- the unsigned halfword (1/65536 turn, as a maps record stores a box heading); the speed, the clock (1/32 s) and the lap signed.
-- The crew (stage 4 recon §1.1): the live objects (bit 31 of +0) among pool objects 0-5 of [0x501350], in slot order; n is 0
-- when the pool pointer is not in RAM. Bit 7 of the flags is the park flag `pitpark` sets; the smoke counter rises from 0 when
-- the car hits a wall (recon §3 item 3: 64 at Diablo Canyon's lane wall).
-- VR_PIT_DAMAGE=<n> (the stage 4 fix wave): the byte n is written to the player's damage flags +0x1ab on every logged frame until
-- the pit handler first runs from the race's green on (the clock counting), so the stop's trigger (0xff222f) picks its work state
-- from them: +0x1ab & 0xf = 0 state 1; else & 3 = 0 state 11; else & 0xc = 0 state 8; else 14.
local path = os.getenv("VR_PIT_LOG")
if path then
  local out = assert(io.open(path, "w"))
  local mem = manager.machine.devices[":maincpu"].spaces["program"]
  local from = tonumber(os.getenv("VR_PIT_FROM") or "1600")
  local frame = 0
  local function f32(a) return (string.unpack("<f", string.pack("<I4", mem:read_u32(a)))) end
  local function s8(a) local v = mem:read_u8(a); return v >= 0x80 and v - 0x100 or v end
  local damage = tonumber(os.getenv("VR_PIT_DAMAGE") or "")
  local last_clock, counting = nil, false
  emu.register_frame_done(function()
    frame = frame + 1
    if frame < from then return end
    local b = 0x400d00
    if damage then
      local clock = mem:read_i32(0x50116c)
      if last_clock and clock > 0 and clock < last_clock then counting = true end
      last_clock = clock
      if counting and mem:read_u32(b + 0xa) == 0xff2345 then damage = nil
      elseif counting then mem:write_u8(b + 0x1ab, damage) end
    end
    local crew = {}
    local pool = mem:read_u32(0x501350)
    if pool >= 0x400000 and pool < 0x600000 then
      for i = 0, 5 do
        local e = pool + 0x280 * i
        if mem:read_u32(e) & 0x80000000 ~= 0 then
          crew[#crew + 1] = string.format("%.4f %.4f %d", f32(e + 0x1e), f32(e + 0x26), mem:read_u16(e + 0x2c))
        end
      end
    end
    out:write(string.format("P %d %d %x %d %d %.4f %.4f %d %d %d %d %d %x %d %d%s%s\n", frame, mem:read_u16(b + 0x150),
      mem:read_u32(b + 0xa), mem:read_u16(b + 0x191), mem:read_u8(b + 0x1bf), f32(b + 0x1e), f32(b + 0x26), mem:read_u16(b + 0x6a),
      mem:read_i32(b + 0x14), mem:read_i32(0x50116c), mem:read_u8(b + 0x57), s8(b + 0x1b5), mem:read_u32(b), mem:read_u8(b + 0x1aa),
      #crew, #crew > 0 and " " or "", table.concat(crew, " ")))
    if frame % 50 == 0 then out:flush() end
  end)
end
