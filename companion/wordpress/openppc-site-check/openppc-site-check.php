<?php
// SPDX-License-Identifier: MIT
/**
 * Plugin Name:       OpenPPC Site Check
 * Plugin URI:        https://github.com/secondsteplabs/openppc/tree/main/companion/wordpress
 * Description:       Adds five checks to Tools > Site Health: whether search engines may index the site, the home page's search basics, the ad and analytics tags in its HTML, a consent banner, and a sitemap in robots.txt. It reads only your own site and sends nothing anywhere.
 * Version:           0.1.0
 * Requires at least: 5.8
 * Requires PHP:      7.4
 * Author:            Second Step
 * License:           MIT
 * License URI:       https://opensource.org/licenses/MIT
 * Text Domain:       openppc-site-check
 *
 * @package OpenPPC_Site_Check
 */

defined( 'ABSPATH' ) || exit;

const OPENPPC_SITE_CHECK_SECONDS = 10;
const OPENPPC_SITE_CHECK_BYTES   = 2097152; // Of a page read: 2 MB.
const OPENPPC_SITE_CHECK_REST    = 'openppc-site-check/v1';
// The checks that read a page run after Site Health opens (async), so it doesn't wait for them.
const OPENPPC_SITE_CHECK_ASYNC = array( 'seo', 'tags', 'consent', 'sitemap' );
// Consent plugins by their folder name in wp-content/plugins.
const OPENPPC_SITE_CHECK_CONSENT_PLUGINS = array(
	'complianz-gdpr'              => 'Complianz',
	'cookie-notice'               => 'Cookie Notice',
	'cookie-law-info'             => 'CookieYes',
	'cookiebot'                   => 'Cookiebot',
	'borlabs-cookie'              => 'Borlabs Cookie',
	'iubenda-cookie-law-solution' => 'iubenda',
	'gdpr-cookie-compliance'      => 'GDPR Cookie Compliance',
	'real-cookie-banner'          => 'Real Cookie Banner',
	'uk-cookie-consent'           => 'Termly',
	'cookie-script-com'           => 'Cookie-Script',
);

/**
 * The crawler's tag list (openppc_online/siteaudit/signatures.json), shipped with the plugin.
 */
function openppc_site_check_signatures(): array {
	static $signatures = null;
	if ( null === $signatures ) {
		// phpcs:ignore WordPress.WP.AlternativeFunctions.file_get_contents_file_get_contents -- a file in this plugin.
		$decoded    = json_decode( (string) file_get_contents( __DIR__ . '/signatures.json' ), true );
		$signatures = is_array( $decoded ) ? $decoded : array();
	}
	return $signatures;
}

/**
 * What the page is missing for search: a list of short problems, empty when it has the basics.
 *
 * @param string $html          The page.
 * @param string $robots_header Its X-Robots-Tag header.
 */
function openppc_site_check_seo( string $html, string $robots_header = '' ): array {
	if ( '' === trim( $html ) ) {
		return array( __( 'no content at all', 'openppc-site-check' ) );
	}
	$doc      = new DOMDocument();
	$previous = libxml_use_internal_errors( true );
	$doc->loadHTML( '<?xml encoding="utf-8"?>' . $html );
	libxml_clear_errors();
	libxml_use_internal_errors( $previous );
	$xpath    = new DOMXPath( $doc );
	$meta     = function ( string $name ) use ( $xpath ): string {
		$lower = "translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')";
		$node  = $xpath->query( "//meta[$lower='$name']/@content" )->item( 0 );
		// phpcs:ignore WordPress.NamingConventions.ValidVariableName.UsedPropertyNotSnakeCase -- DOM's name.
		return $node ? trim( $node->nodeValue ) : '';
	};
	$problems = array();
	if ( '' === trim( (string) $xpath->evaluate( 'string(//title)' ) ) ) {
		$problems[] = __( 'no title', 'openppc-site-check' );
	}
	if ( '' === $meta( 'description' ) ) {
		$problems[] = __( 'no meta description', 'openppc-site-check' );
	}
	$h1 = $xpath->query( '//h1' )->length;
	if ( 1 !== $h1 ) {
		/* translators: %d: how many h1 headings the page has */
		$problems[] = sprintf( __( '%d h1 headings instead of one', 'openppc-site-check' ), $h1 );
	}
	if ( ! $xpath->query( "//link[contains(concat(' ', normalize-space(@rel), ' '), ' canonical ')]" )->length ) {
		$problems[] = __( 'no canonical link', 'openppc-site-check' );
	}
	if ( false !== stripos( $meta( 'robots' ) . ' ' . $robots_header, 'noindex' ) ) {
		$problems[] = __( 'it asks search engines not to index it (noindex)', 'openppc-site-check' );
	}
	if ( '' === $meta( 'viewport' ) ) {
		$problems[] = __( 'no viewport meta tag, so phones show it zoomed out', 'openppc-site-check' );
	}
	if ( '' === trim( (string) $xpath->evaluate( 'string(/html/@lang)' ) ) ) {
		$problems[] = __( 'no lang attribute on the html element', 'openppc-site-check' );
	}
	return $problems;
}

/**
 * The vendors whose code or ID pattern is in the text, as the crawler's tags.in_text finds them: id => array( name, kind ).
 *
 * @param string $text       The page's HTML.
 * @param array  $signatures The tag list.
 */
function openppc_site_check_tags( string $text, array $signatures ): array {
	$found = array();
	foreach ( $signatures['vendors'] ?? array() as $vendor ) {
		foreach ( $vendor['source'] ?? array() as $pattern ) {
			// A pattern that fails (PCRE's backtracking limit) counts as no match.
			if ( 1 === preg_match( '~' . str_replace( '~', '\~', $pattern ) . '~', $text ) ) {
				$found[ $vendor['id'] ] = array( $vendor['name'], $vendor['kind'] );
				break;
			}
		}
	}
	return $found;
}

/**
 * The consent banner the page or an active plugin brings, or '' when there is none.
 *
 * @param string $html           The page.
 * @param array  $signatures     The tag list.
 * @param array  $active_plugins The active_plugins option.
 */
function openppc_site_check_consent( string $html, array $signatures, array $active_plugins ): string {
	foreach ( $signatures['consent'] ?? array() as $banner ) {
		foreach ( $banner['hosts'] as $host ) {
			if ( false !== stripos( $html, $host ) ) {
				return $banner['name'];
			}
		}
	}
	foreach ( $active_plugins as $plugin ) {
		$folder = strtok( (string) $plugin, '/' );
		if ( isset( OPENPPC_SITE_CHECK_CONSENT_PLUGINS[ $folder ] ) ) {
			return OPENPPC_SITE_CHECK_CONSENT_PLUGINS[ $folder ];
		}
	}
	return false !== strpos( $html, '__tcfapi' ) ? __( 'an IAB TCF banner', 'openppc-site-check' ) : '';
}

/**
 * Whether robots.txt names a sitemap.
 *
 * @param string $robots_txt The file.
 */
function openppc_site_check_has_sitemap( string $robots_txt ): bool {
	return (bool) preg_match( '/^\s*sitemap\s*:\s*\S/im', $robots_txt );
}

/**
 * A page of this site, fetched once per request and never followed elsewhere: array( body, X-Robots-Tag ), or why it
 * could not be read.
 *
 * @param string $path The page's path.
 * @return array|string
 */
function openppc_site_check_fetch( string $path ) {
	static $pages = array();
	if ( ! isset( $pages[ $path ] ) ) {
		$response = wp_remote_get(
			home_url( $path ),
			array(
				'timeout'             => OPENPPC_SITE_CHECK_SECONDS,
				'redirection'         => 0,
				'limit_response_size' => OPENPPC_SITE_CHECK_BYTES,
				// The site's own address, read as Site Health's loopback test reads it, by core's filter.
				'sslverify'           => apply_filters( 'https_local_ssl_verify', false ), // phpcs:ignore WordPress.NamingConventions.PrefixAllGlobals.NonPrefixedHooknameFound
			)
		);
		$code     = is_wp_error( $response ) ? 0 : (int) wp_remote_retrieve_response_code( $response );
		if ( is_wp_error( $response ) ) {
			$pages[ $path ] = $response->get_error_message();
		} elseif ( $code >= 300 && $code < 400 ) {
			/* translators: 1: the HTTP status code, 2: the address it redirects to */
			$pages[ $path ] = sprintf( __( 'it redirects (HTTP %1$d) to %2$s', 'openppc-site-check' ), $code, (string) wp_remote_retrieve_header( $response, 'location' ) );
		} elseif ( 200 !== $code ) {
			/* translators: %d: the HTTP status code */
			$pages[ $path ] = sprintf( __( 'it answered HTTP %d', 'openppc-site-check' ), $code );
		} else {
			$pages[ $path ] = array( wp_remote_retrieve_body( $response ), (string) wp_remote_retrieve_header( $response, 'x-robots-tag' ) );
		}
	}
	return $pages[ $path ];
}

/**
 * A Site Health result. Site Health prints the label and badge as text, and the description and actions as HTML.
 *
 * @param string $test        The check's id.
 * @param string $status      good, recommended or critical.
 * @param string $label       The headline.
 * @param string $description What was found, as text.
 */
function openppc_site_check_result( string $test, string $status, string $label, string $description ): array {
	$command = 'openppc-online site ' . home_url( '/' ) . ' --render';
	return array(
		'test'        => $test,
		'status'      => $status,
		'label'       => $label,
		'badge'       => array(
			'label' => __( 'OpenPPC', 'openppc-site-check' ),
			'color' => 'blue',
		),
		'description' => '<p>' . esc_html( $description ) . '</p>',
		'actions'     => '<p>' . esc_html__( 'For every page, in a real browser, before and after consent:', 'openppc-site-check' )
			. ' <code>' . esc_html( $command ) . '</code></p>',
	);
}

/**
 * The result when a page of the site could not be read.
 *
 * @param string $test The check's id.
 * @param string $what The page.
 * @param string $why  Why it could not be read.
 */
function openppc_site_check_unreachable( string $test, string $what, string $why ): array {
	/* translators: 1: the page, 2: why it could not be read */
	$text = sprintf( __( 'WordPress could not read its own %1$s: %2$s.', 'openppc-site-check' ), $what, $why );
	/* translators: %s: the page */
	$label = sprintf( __( 'OpenPPC could not read the %s', 'openppc-site-check' ), $what );
	return openppc_site_check_result( $test, 'recommended', $label, $text );
}

/**
 * Settings > Reading: may search engines index the site?
 */
function openppc_site_check_test_indexing(): array {
	if ( '0' === (string) get_option( 'blog_public' ) ) {
		return openppc_site_check_result(
			'openppc_indexing',
			'critical',
			__( 'Search engines are asked not to index this site', 'openppc-site-check' ),
			__( 'Settings > Reading has "Discourage search engines from indexing this site" ticked, so ads can run but the site will not show in search results. Untick it when the site is live.', 'openppc-site-check' )
		);
	}
	return openppc_site_check_result( 'openppc_indexing', 'good', __( 'Search engines may index this site', 'openppc-site-check' ), __( 'Settings > Reading lets search engines index the site.', 'openppc-site-check' ) );
}

/**
 * The home page's search basics.
 */
function openppc_site_check_test_seo(): array {
	$page = openppc_site_check_fetch( '/' );
	if ( ! is_array( $page ) ) {
		return openppc_site_check_unreachable( 'openppc_seo', __( 'home page', 'openppc-site-check' ), $page );
	}
	$problems = openppc_site_check_seo( $page[0], $page[1] );
	if ( $problems ) {
		/* translators: %s: a list of problems */
		$text = sprintf( __( 'The home page has %s.', 'openppc-site-check' ), implode( '; ', $problems ) );
		return openppc_site_check_result( 'openppc_seo', 'recommended', __( 'The home page is missing search basics', 'openppc-site-check' ), $text );
	}
	return openppc_site_check_result( 'openppc_seo', 'good', __( 'The home page has the search basics', 'openppc-site-check' ), __( 'It has a title, a meta description, one h1, a canonical link, a viewport and a language, and it may be indexed.', 'openppc-site-check' ) );
}

/**
 * The tags that measure visits and conversions.
 *
 * @param array $tags id => array( name, kind ).
 */
function openppc_site_check_measuring_tags( array $tags ): array {
	return array_filter( $tags, fn( $tag ) => in_array( $tag[1], array( 'ads', 'analytics', 'tag manager' ), true ) );
}

/**
 * The ad and analytics tags in the home page's HTML.
 */
function openppc_site_check_test_tags(): array {
	$page = openppc_site_check_fetch( '/' );
	if ( ! is_array( $page ) ) {
		return openppc_site_check_unreachable( 'openppc_tags', __( 'home page', 'openppc-site-check' ), $page );
	}
	$tags = openppc_site_check_measuring_tags( openppc_site_check_tags( $page[0], openppc_site_check_signatures() ) );
	if ( ! $tags ) {
		return openppc_site_check_result( 'openppc_tags', 'recommended', __( 'No ad or analytics tag in the home page', 'openppc-site-check' ), __( 'The home page\'s HTML has no known analytics, ad or tag manager code, so visits and conversions may not be measured. A tag added by a script after the page loads only shows in a real browser.', 'openppc-site-check' ) );
	}
	/* translators: %s: a list of tag names */
	$text = sprintf( __( 'The home page\'s HTML loads %s. Whether each one fires, and with which events, shows only in a real browser.', 'openppc-site-check' ), implode( ', ', array_column( $tags, 0 ) ) );
	return openppc_site_check_result( 'openppc_tags', 'good', __( 'The home page has ad or analytics tags', 'openppc-site-check' ), $text );
}

/**
 * A consent banner, when the home page has tags that need one.
 */
function openppc_site_check_test_consent(): array {
	$page = openppc_site_check_fetch( '/' );
	if ( ! is_array( $page ) ) {
		return openppc_site_check_unreachable( 'openppc_consent', __( 'home page', 'openppc-site-check' ), $page );
	}
	$signatures = openppc_site_check_signatures();
	$banner     = openppc_site_check_consent( $page[0], $signatures, (array) get_option( 'active_plugins', array() ) );
	$tags       = openppc_site_check_measuring_tags( openppc_site_check_tags( $page[0], $signatures ) );
	if ( '' !== $banner ) {
		/* translators: %s: the consent banner's name */
		$text = sprintf( __( 'Found %s. Whether tags wait for consent shows only in a real browser.', 'openppc-site-check' ), $banner );
		return openppc_site_check_result( 'openppc_consent', 'good', __( 'The site has a consent banner', 'openppc-site-check' ), $text );
	}
	if ( ! $tags ) {
		return openppc_site_check_result( 'openppc_consent', 'good', __( 'No consent banner, and no tag that needs one', 'openppc-site-check' ), __( 'The home page has no known consent banner and no known ad or analytics tag.', 'openppc-site-check' ) );
	}
	return openppc_site_check_result( 'openppc_consent', 'recommended', __( 'Tags but no consent banner', 'openppc-site-check' ), __( 'The home page loads ad or analytics tags but no known consent banner. Visitors in the EU, the UK and some US states must be asked before ad and analytics cookies are set.', 'openppc-site-check' ) );
}

/**
 * A sitemap named in robots.txt.
 */
function openppc_site_check_test_sitemap(): array {
	$page = openppc_site_check_fetch( '/robots.txt' );
	if ( ! is_array( $page ) ) {
		return openppc_site_check_unreachable( 'openppc_sitemap', 'robots.txt', $page );
	}
	if ( openppc_site_check_has_sitemap( $page[0] ) ) {
		return openppc_site_check_result( 'openppc_sitemap', 'good', __( 'robots.txt names a sitemap', 'openppc-site-check' ), __( 'Search engines find every page from the sitemap that robots.txt names.', 'openppc-site-check' ) );
	}
	return openppc_site_check_result( 'openppc_sitemap', 'recommended', __( 'robots.txt names no sitemap', 'openppc-site-check' ), __( 'Add a Sitemap: line to robots.txt (WordPress adds /wp-sitemap.xml unless a plugin turned it off) so search engines find every page.', 'openppc-site-check' ) );
}

add_filter(
	'site_status_tests',
	function ( array $tests ): array {
		$labels = array(
			'indexing' => __( 'Search engines may index the site', 'openppc-site-check' ),
			'seo'      => __( 'The home page has the search basics', 'openppc-site-check' ),
			'tags'     => __( 'The home page has ad or analytics tags', 'openppc-site-check' ),
			'consent'  => __( 'Tags have a consent banner', 'openppc-site-check' ),
			'sitemap'  => __( 'robots.txt names a sitemap', 'openppc-site-check' ),
		);

		$tests['direct']['openppc_indexing'] = array(
			'label' => $labels['indexing'],
			'test'  => 'openppc_site_check_test_indexing',
		);
		foreach ( OPENPPC_SITE_CHECK_ASYNC as $name ) {
			$tests['async'][ 'openppc_' . $name ] = array(
				'label'             => $labels[ $name ],
				'test'              => rest_url( OPENPPC_SITE_CHECK_REST . '/' . $name ),
				'has_rest'          => true,
				'async_direct_test' => 'openppc_site_check_test_' . $name,
			);
		}
		return $tests;
	}
);

add_action(
	'rest_api_init',
	function () {
		foreach ( OPENPPC_SITE_CHECK_ASYNC as $name ) {
			register_rest_route(
				OPENPPC_SITE_CHECK_REST,
				'/' . $name,
				array(
					'methods'             => 'GET',
					'callback'            => 'openppc_site_check_test_' . $name,
					'permission_callback' => fn() => current_user_can( 'view_site_health_checks' ),
				)
			);
		}
	}
);
