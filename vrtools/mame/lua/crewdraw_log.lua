-- Phase 26 stage 4 (Task 5): what the pit crew's animation pushes to the TGP through the figure routines, loaded by autoplay.lua
-- when VR_CREW_DRAW_LOG names a file. The crew runs the start figures' character code, whose world-axis uses of the animation (the
-- root offset's x and z where the draw pushes it and where an ended animation adds it to the position, the body's two rotations
-- about the horizontal axes) call the routines `figrootx`, `figrootz`, `figrot0`, `figrot2` (direction.FIGURE_SITES); each word
-- the V60 writes to the TGP FIFO (autoplay.lua's tap, vr_on_fifo_word) while the PC lies in VR_CREW_DRAW_PCS ("lo-hi", hex: those
-- routines' span in the directory image) and R25 is one of pool objects 0-5 of [0x501350] is logged, on the frames the player's
-- handler is the pit handler 0xff2345 (one frame late: the handler read at each frame end gates the next frame):
--   D <frame> <object 0-5> <pc hex> <word hex>
-- frame counted from 1 at the first frame end, as pit_log.lua: a word pushed while frame f is emulated carries f.
local path = os.getenv("VR_CREW_DRAW_LOG")
local span = os.getenv("VR_CREW_DRAW_PCS")
if path and span and _G.vr_on_fifo_word then
  local out = assert(io.open(path, "w"))
  local cpu = manager.machine.devices[":maincpu"]
  local mem = cpu.spaces["program"]
  local a, b = string.match(span, "(%x+)%-(%x+)")
  local lo, hi = tonumber(a, 16), tonumber(b, 16)
  local frame, active = 0, false
  local pc_state, r25_state = cpu.state["PC"], cpu.state["R25"]
  _G.vr_on_fifo_word(function(word, _)
    if not active then return end
    local pc = pc_state.value
    if pc < lo or pc >= hi then return end
    local pool = mem:read_u32(0x501350)
    local k = r25_state.value - pool
    if k < 0 or k % 0x280 ~= 0 or k >= 6 * 0x280 then return end
    out:write(string.format("D %d %d %x %08x\n", frame + 1, k // 0x280, pc, word))
  end)
  emu.register_frame_done(function()
    frame = frame + 1
    active = mem:read_u32(0x400d00 + 0xa) == 0xff2345
    if frame % 50 == 0 then out:flush() end
  end)
end
