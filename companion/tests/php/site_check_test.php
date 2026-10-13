<?php
// SPDX-License-Identifier: MIT
// The WordPress plugin's checks against canned pages, with WordPress stubbed out, and the tag cases the crawler
// passes too (../tag_cases.json). Run with PHP 7.4 or later: php companion/tests/php/site_check_test.php

define( 'ABSPATH', __DIR__ );

$filters = array();
$actions = array();
$routes  = array();
$options = array( 'blog_public' => '1', 'active_plugins' => array() );
$caps    = array( 'view_site_health_checks' => true );
$pages   = array();
$fetched = array();

function add_filter( $name, $callback ) { $GLOBALS['filters'][ $name ] = $callback; }
function add_action( $name, $callback ) { $GLOBALS['actions'][ $name ] = $callback; }
function apply_filters( $name, $value ) { return $value; }
function __( $text, $domain ) { return $text; }
function esc_html( $text ) { return htmlspecialchars( $text, ENT_QUOTES ); }
function esc_html__( $text, $domain ) { return esc_html( $text ); }
function home_url( $path = '' ) { return 'https://shop.example' . $path; }
function rest_url( $path ) { return 'https://shop.example/wp-json/' . $path; }
function register_rest_route( $namespace, $route, $args ) { $GLOBALS['routes'][ "$namespace$route" ] = $args; }
function current_user_can( $cap ) { return $GLOBALS['caps'][ $cap ] ?? false; }
function get_option( $name, $default = false ) { return $GLOBALS['options'][ $name ] ?? $default; }
function is_wp_error( $thing ) { return $thing instanceof WP_Error; }
function wp_remote_retrieve_response_code( $r ) { return $r['code']; }
function wp_remote_retrieve_body( $r ) { return $r['body']; }
function wp_remote_retrieve_header( $r, $name ) { return $r['headers'][ $name ] ?? ''; }
function wp_remote_get( $url, $args ) {
	$GLOBALS['fetched'][] = array( $url, $args['redirection'], $args['limit_response_size'] );
	return $GLOBALS['pages'][ $url ] ?? new WP_Error( 'cURL error 7: Failed to connect' );
}
class WP_Error {
	private $message;
	function __construct( $message ) { $this->message = $message; }
	function get_error_message() { return $this->message; }
}

require __DIR__ . '/../../wordpress/openppc-site-check/openppc-site-check.php';

$failed = 0;
function check( $ok, $what ) {
	global $failed;
	if ( ! $ok ) {
		$failed++;
		fwrite( STDERR, "FAIL: $what\n" );
	}
}

// case => array( the home page's answer, what the check must say )
const UNREADABLE = array(
	'redirect' => array( array( 'code' => 301, 'body' => '', 'headers' => array( 'location' => 'https://elsewhere.example/<b>' ) ),
		'it redirects (HTTP 301) to https://elsewhere.example/&lt;b&gt;' ),
	'down'     => array( array( 'code' => 503, 'body' => 'down', 'headers' => array() ), 'it answered HTTP 503' ),
	'error'    => array( null, 'cURL error 7: Failed to connect' ),
);
$case = $argv[1] ?? '';
if ( isset( UNREADABLE[ $case ] ) ) {
	list( $answer, $expect ) = UNREADABLE[ $case ];
	$pages = $answer ? array( 'https://shop.example/' => $answer ) : array();
	$r     = openppc_site_check_test_seo();
	check( $r['status'] === 'recommended' && $r['label'] === 'OpenPPC could not read the home page', "$case: {$r['label']}" );
	check( strpos( $r['description'], $expect ) !== false, "$case: {$r['description']}" );
	check( count( $fetched ) === 1, "$case: one request, no redirect followed" );
	echo $failed ? '' : "$case passed\n";
	exit( $failed ? 1 : 0 );
}

$signatures = openppc_site_check_signatures();
check( count( $signatures['vendors'] ) > 10, 'the tag list loads' );
$cases = json_decode( file_get_contents( __DIR__ . '/../tag_cases.json' ), true );
check( count( $cases['in_text'] ) > 5, 'the shared cases load' );
foreach ( $cases['in_text'] as list( $text, $expected ) ) {
	$found = array_keys( openppc_site_check_tags( $text, $signatures ) );
	sort( $found );
	check( $found === $expected, 'in_text(' . $text . '): ' . implode( ', ', $found ) );
}

$good = '<!doctype html><html lang="en"><head><title>Shop</title>'
	. '<meta name="Description" content="Plumbing parts"><meta name="viewport" content="width=device-width">'
	. '<link rel="canonical" href="https://shop.example/">'
	. '<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABC123XYZ"></script>'
	. "<script>gtag('config', 'G-ABC123XYZ'); fbq('init', '1234');</script>"
	. '<script src="https://cdn.cookielaw.org/scripttemplates/otSDKStub.js"></script>'
	. '</head><body><h1>Parts</h1></body></html>';
check( openppc_site_check_seo( $good ) === array(), 'a page with the basics has no problems' );
$bad = openppc_site_check_seo( '<html><head><meta name="robots" content="noindex"></head><body><h1>a</h1><h1>b</h1></body></html>' );
check( $bad === array( 'no title', 'no meta description', '2 h1 headings instead of one', 'no canonical link',
	'it asks search engines not to index it (noindex)', 'no viewport meta tag, so phones show it zoomed out',
	'no lang attribute on the html element' ), 'every missing basic is named: ' . implode( '; ', $bad ) );
check( in_array( 'it asks search engines not to index it (noindex)', openppc_site_check_seo( $good, 'noindex, nofollow' ), true ),
	'an X-Robots-Tag noindex header counts' );
check( openppc_site_check_seo( " \n" ) === array( 'no content at all' ), 'an empty page is a problem, not a crash' );

check( array_keys( openppc_site_check_tags( $good, $signatures ) ) === array( 'ga4', 'meta' ), 'tags are found by their code' );
check( openppc_site_check_consent( $good, $signatures, array() ) === 'OneTrust', 'a banner is found by its host' );
check( openppc_site_check_consent( '', $signatures, array( 'complianz-gdpr/complianz-gpdr.php' ) ) === 'Complianz',
	'a banner is found by its plugin' );
check( openppc_site_check_consent( '<p>none</p>', $signatures, array( 'akismet/akismet.php' ) ) === '', 'no banner is no banner' );
check( openppc_site_check_consent( '<script>window.__tcfapi = function(){}</script>', $signatures, array() ) === 'an IAB TCF banner',
	'a TCF API counts as a banner' );
check( openppc_site_check_has_sitemap( "User-agent: *\nDisallow:\n\nSitemap: https://shop.example/wp-sitemap.xml\n" ), 'a Sitemap line' );
check( ! openppc_site_check_has_sitemap( "User-agent: *\n# Sitemap: later\n" ), 'a commented Sitemap is no sitemap' );
$slow = array( 'vendors' => array( array( 'id' => 'slow', 'name' => 'Slow', 'kind' => 'ads', 'source' => array( '(a+)+$' ) ) ) );
check( openppc_site_check_tags( str_repeat( 'a', 5000 ) . 'b', $slow ) === array(), 'a pattern that gives up counts as no match' );

$tests = $filters['site_status_tests']( array( 'direct' => array(), 'async' => array() ) );
check( array_keys( $tests['direct'] ) === array( 'openppc_indexing' ), 'the check that reads no page runs as Site Health opens' );
check( array_keys( $tests['async'] ) === array( 'openppc_seo', 'openppc_tags', 'openppc_consent', 'openppc_sitemap' ),
	'the four that read a page run after it opens' );
$actions['rest_api_init']();
foreach ( $tests['async'] as $id => $test ) {
	$name = substr( $id, strlen( 'openppc_' ) );
	check( $test['has_rest'] && $test['test'] === "https://shop.example/wp-json/openppc-site-check/v1/$name", "$id is a REST check" );
	$route = $routes[ "openppc-site-check/v1/$name" ] ?? null;
	check( $route && $route['methods'] === 'GET' && $route['callback'] === $test['async_direct_test'], "$id has its route" );
	check( $route && ( $route['permission_callback'] )(), "$id answers whoever may see Site Health" );
}
$caps = array();
foreach ( $routes as $path => $route ) {
	check( ! ( $route['permission_callback'] )(), "$path refuses whoever may not see Site Health" );
}

$run = function () use ( $tests ) {
	$results = array();
	foreach ( array( 'openppc_indexing' => $tests['direct']['openppc_indexing']['test'] )
		+ array_map( fn( $t ) => $t['async_direct_test'], $tests['async'] ) as $id => $callable ) {
		check( is_callable( $callable ), "$id is callable" );
		$results[ $id ] = call_user_func( $callable );
		check( $results[ $id ]['test'] === $id, "$id names itself" );
	}
	return $results;
};

$pages   = array(
	'https://shop.example/'           => array( 'code' => 200, 'body' => $good, 'headers' => array() ),
	'https://shop.example/robots.txt' => array( 'code' => 200, 'body' => "Sitemap: https://shop.example/wp-sitemap.xml\n", 'headers' => array() ),
);
$results = $run();
foreach ( $results as $id => $r ) {
	check( $r['status'] === 'good', "$id is good on a good site: {$r['description']}" );
	check( strpos( $r['actions'], 'openppc-online site https://shop.example/ --render' ) !== false, "$id suggests the full check" );
}
check( strpos( $results['openppc_tags']['description'], 'Google Analytics 4, Meta Pixel' ) !== false, 'the tags are listed' );
check( $fetched === array( array( 'https://shop.example/', 0, 2097152 ), array( 'https://shop.example/robots.txt', 0, 2097152 ) ),
	'each page is fetched once, only from this site, following no redirect, at most 2 MB' );

$options['blog_public'] = '0';
check( call_user_func( $tests['direct']['openppc_indexing']['test'] )['status'] === 'critical', 'a hidden site is critical' );
$noisy = str_replace( '<script src="https://cdn.cookielaw.org/scripttemplates/otSDKStub.js"></script>', '', $good );
check( openppc_site_check_consent( $noisy, $signatures, array() ) === '' && openppc_site_check_tags( $noisy, $signatures ),
	'tags without a banner' );
$escaped = openppc_site_check_result( 'x', 'good', 'label', '<script>alert(1)</script>' );
check( strpos( $escaped['description'], '<script>' ) === false, 'descriptions are escaped' );

// The fetcher keeps its pages for one request, so each unreadable home page runs in a process of its own.
foreach ( array_keys( UNREADABLE ) as $case ) {
	$out = shell_exec( escapeshellarg( PHP_BINARY ) . ' ' . escapeshellarg( __FILE__ ) . " $case 2>&1" );
	check( trim( (string) $out ) === "$case passed", "the $case case: $out" );
}

if ( $failed ) {
	fwrite( STDERR, "$failed failed\n" );
	exit( 1 );
}
echo "all passed\n";
