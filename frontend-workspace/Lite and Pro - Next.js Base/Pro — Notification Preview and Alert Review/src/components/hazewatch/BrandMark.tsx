import Image from "next/image";

/** The supplied brand asset is the full lockup - circular mark plus the
 * "HazeWatch" wordmark - so the shells no longer print the name beside it.
 * They carry a visually-hidden <h1> instead, which is also where the "AI" in
 * the product name survives now that the wordmark itself omits it.
 *
 * `alt` is deliberately empty: the lockup is decorative once that heading
 * names the product, and a filled alt would make screen readers say it twice.
 */
export function BrandMark() {
  return (
    <Image
      src="/hazewatch-logo.png"
      alt=""
      width={1200}
      height={401}
      priority
      className="h-auto w-[200px]"
    />
  );
}
