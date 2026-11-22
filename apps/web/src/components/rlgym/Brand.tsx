/* ADI Labs Forge branding (design shared/BRANDING.md, RL Gym work package 2.13). One place holds the product name, so
   a future rename is one line. */

export const FAMILY = 'ADI Labs Forge';
export const PRODUCT = 'RL Gym Evaluation';
/** On screen, the sibling products are called by these names. */
export const AUTHORING = 'Authoring';
export const STUDIO = 'Studio';

export function pageTitle(page?: string) {
  return [page, PRODUCT, FAMILY].filter(Boolean).join(' · ');
}

export function BrandLockup({
  tone = 'dark',
  size = 'header',
}: {
  tone?: 'dark' | 'light';
  size?: 'header' | 'signin';
}) {
  const signin = size === 'signin';
  return (
    <a
      href="/gym"
      className={`brand-lockup ${tone} ${size}`}
      aria-label={`${FAMILY} · ${PRODUCT} home`}
    >
      <img
        src={signin ? '/brand/adi-labs-forge-mark-240.png' : '/brand/adi-labs-forge-mark-96.png'}
        alt=""
        width={signin ? 112 : 30}
        height={signin ? 112 : 30}
      />
      <span className="brand-words">
        <span className="brand-name">
          ADI LABS<span className="brand-forge">-FORGE</span>
        </span>
        <span className="brand-divider" aria-hidden="true" />
        <span className="brand-product">{PRODUCT.toUpperCase()}</span>
      </span>
    </a>
  );
}
