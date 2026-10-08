package com.fixedseed.passthrough.mixin;

import com.fixedseed.passthrough.MobWar;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.entity.projectile.Projectile;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Steve's arrows and rockets fly through proxies: the host traces them into its real people itself. */
@Mixin(Projectile.class)
abstract class ProjectileMixin {
	@Shadow
	public abstract Entity getOwner();

	@Inject(method = "canHitEntity(Lnet/minecraft/world/entity/Entity;)Z", at = @At("HEAD"), cancellable = true)
	private void passthrough$throughProxies(final Entity target, final CallbackInfoReturnable<Boolean> cir) {
		if (MobWar.isProxy(target) && this.getOwner() instanceof Player) {
			cir.setReturnValue(false);
		}
	}
}
