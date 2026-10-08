package com.fixedseed.passthrough.client.mixin;

import com.fixedseed.passthrough.client.HostState;
import net.minecraft.client.Camera;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * In third person the host camera sits behind and beside the player, so aim along the camera's ray (what is under
 * the crosshair) instead of from the player's eyes. The ray starts level with the player and reaches `range` past.
 */
@Mixin(Entity.class)
abstract class EntityPickMixin {
	@Inject(method = "pick(DFZ)Lnet/minecraft/world/phys/HitResult;", at = @At("HEAD"), cancellable = true)
	private void passthrough$cameraRay(final double range, final float a, final boolean withLiquids, final CallbackInfoReturnable<HitResult> cir) {
		HostState.Pose p = HostState.frame();
		if (p == null || p.firstPerson() || !((Object) this instanceof LocalPlayer self)) {
			return;
		}

		Camera camera = Minecraft.getInstance().gameRenderer.mainCamera();
		Vec3 from = camera.position();
		Vec3 dir = new Vec3(camera.forwardVector()).normalize();
		double along = Math.max(0.0, self.getEyePosition(a).subtract(from).dot(dir));
		Vec3 start = from.add(dir.scale(Math.max(0.0, along - 0.4)));
		Vec3 end = from.add(dir.scale(along + range));
		ClipContext.Fluid fluid = withLiquids ? ClipContext.Fluid.ANY : ClipContext.Fluid.NONE;
		cir.setReturnValue(self.level().clip(new ClipContext(start, end, ClipContext.Block.OUTLINE, fluid, self)));
	}
}
