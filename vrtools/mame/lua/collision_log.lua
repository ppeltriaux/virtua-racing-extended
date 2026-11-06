-- Collision probe: the player's TGP collision call and its result, once per logic frame.
-- The player's car makes five calls per logic frame (centre, then four wheels within a few units); opponents
-- make one call each on the other frames. A frame is logged when its first five calls are that cluster.
-- Env: VR_COLLISION_LOG (absolute path). Lines: C <frame> <y> <id> <x> <z> <result_y> <quad>, END <frame>.
local out = assert(io.open(os.getenv("VR_COLLISION_LOG"), "w"))
local v60 = manager.machine.devices[":maincpu"]
local prog, iosp = v60.spaces["program"], v60.spaces["io"]
local frame, lo, pending, got = 0, nil, nil, nil
local params, want_result, rlo = {}, false, nil
local calls = {}                       -- this frame's completed calls
local taps = {}
_G.vr_collision_taps = taps
local function f32(u) return (string.unpack("<f", string.pack("<I4", u))) end
local function emit()
  calls[#calls + 1] = params
end
local function flush_frame()
  if #calls >= 5 then
    local c = calls[1]
    local x, z = f32(c[3]), f32(c[4])
    local cluster = true
    for i = 2, 5 do
      local dx, dz = f32(calls[i][3]) - x, f32(calls[i][4]) - z
      if dx * dx + dz * dz > 36 then cluster = false end
    end
    if cluster then
      out:write(string.format("C %d %.3f %x %.3f %.3f %.3f %x\n", frame, f32(c[1]), c[2], x, z, f32(c[5]), c[6]))
      _G.vr_player = {frame = frame, x = x, z = z}            -- the player's position this logic frame (autopilot)
    end
  end
  calls = {}
end
-- FIFO-in words come from autoplay's single FIFO tap (vr_on_fifo_word)
assert(type(_G.vr_on_fifo_word) == "function", "collision_log.lua must be loaded by autoplay.lua")
_G.vr_on_fifo_word(function(w, _)
  if pending then
    pending[#pending + 1] = w
    if #pending == 4 then params = pending; pending = nil; want_result = true end
  elseif w == 0x1b010000 then pending = {} end
end)
-- result words: after writing 0x8001 to the RAM address port, the next two 32-bit I/O reads at 0xd20000 are y and quad
taps[#taps + 1] = prog:install_write_tap(0xd00000, 0xd00001, "col_ramadr", function(offset, data, mask)
  if want_result and (data & 0xffff) == 0x8001 then got = 0 end
end)
local function result_word(w)
  got = got + 1
  if got == 1 then params[5] = w elseif got == 2 then params[6] = w; got = nil; want_result = false; emit() end
end
taps[#taps + 1] = iosp:install_read_tap(0xd20000, 0xd20003, "col_ram", function(offset, data, mask)
  if got == nil then return end
  if mask == 0xffffffff or mask == -1 then result_word(data & 0xffffffff)           -- one 32-bit access
  elseif offset == 0xd20000 then rlo = data & 0xffff                                -- or two halves
  elseif offset == 0xd20002 and rlo then local w = ((data & 0xffff) << 16) | rlo; rlo = nil; result_word(w) end
end)
emu.register_frame_done(function()
  flush_frame()
  frame = frame + 1
  if frame % 100 == 0 then
    -- S line: the selected course (RAM 0x501940) and its data index (0x501934) so a log identifies its course
    local ok, secs = pcall(function() return manager.machine.time.seconds end)
    local rs = (type(_G.vr_race_start) == "function") and _G.vr_race_start() or nil
    out:write(string.format("S %d %x %x %s %s\nEND %d\n", frame, prog:read_u8(0x501940), prog:read_u8(0x501934),
                            ok and tostring(secs) or "?", rs and tostring(rs) or "-", frame)); out:flush()
  end
end)
