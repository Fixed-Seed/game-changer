package com.fixedseed.passthrough.mixin;

import com.fixedseed.passthrough.WorldBridge;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Every block change on the server (placed, broken, blown up) goes to the host, so it can mirror solid blocks. */
@Mixin(Level.class)
abstract class LevelMixin {
	@Inject(method = "setBlock(Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/state/BlockState;II)Z", at = @At("RETURN"))
	private void passthrough$blockChanged(final BlockPos pos, final BlockState state, final int flags, final int limit, final CallbackInfoReturnable<Boolean> cir) {
		if (cir.getReturnValueZ() && (Object) this instanceof ServerLevel level) {
			WorldBridge.onBlockChanged(level, pos, state);
		}
	}
}
