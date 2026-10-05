/* Google Tag Manager for the website pages of openppc.si. The app at /app/ never loads this file, and its own
   security policy blocks every outside connection, so an export can't leave the browser.

   Consent Mode: in the EU, EEA, UK and Switzerland Google gets only cookieless pings; elsewhere analytics
   cookies are on. Advertising cookies stay off everywhere until the site asks for consent. */
window.dataLayer = window.dataLayer || [];
function gtag() { window.dataLayer.push(arguments); }
gtag('consent', 'default', {
  ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied', analytics_storage: 'denied',
  region: ['AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT',
           'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE', 'IS', 'LI', 'NO', 'GB', 'CH']
});
gtag('consent', 'default', {
  ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied', analytics_storage: 'granted'
});
window.dataLayer.push({ 'gtm.start': new Date().getTime(), event: 'gtm.js' });
(function () {
  var tag = document.createElement('script');
  tag.async = true;
  tag.src = 'https://www.googletagmanager.com/gtm.js?id=GTM-MKK8JT53';
  document.head.appendChild(tag);
})();
